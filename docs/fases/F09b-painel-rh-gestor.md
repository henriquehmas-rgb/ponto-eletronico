# F09b — Painel RH e Gestor

| | |
|---|---|
| **Onda** | 3 |
| **Agentes** | 4 · **A1** casca do painel (sessão/login mínimo, RBAC no cliente, layout, navegação) + dashboards de RH/gestor/diretoria (KPIs, gráficos, "quem está trabalhando") · **A2** telas de cadastro (empresas, unidades com mapa e geocerca, departamentos, centros de custo, cargos, equipes, colaboradores, contratos/vínculos, dispositivos, biometria) · **A3** grade de apuração mês × colaborador (virtualizada, tratamento, ocorrências, recálculo, ações em lote) · **A4** escalas e planejamento (turnos, escalas, atribuição, grade visual, previsto × realizado, cobertura por turno) |
| **Duração estimada** | 10 dias |
| **Depende de** | F2 (cadastros organizacionais e pessoas), F3 (motor de jornada), F4 (cálculo e banco de horas), F9a (design system) — **todas concluídas e verificadas contra banco real**. Além disso, **A1 depende da interface fixada de `apps/web/src/lib/sessao/**` (F8, mesma onda)** — não do restante de F8, só do módulo de sessão compartilhado; ver §2 |
| **Criticidade** | Alta — é a primeira fase de `apps/web` que faz chamada real à API de gestão (F9a só usou dados fixos em Storybook). F10 (fechamento) e F11 (relatórios) partem do que esta fase deixa pronto na área de gestão. O login em si **não é construído aqui** — é reuso do módulo compartilhado da F8, coordenado pelo orquestrador (§2) |
| **Branch** | `f09b-painel-rh-gestor` |

---

## 1. Objetivo

Ao fim desta fase, **`/painel` deixa de ser `PlaceholderDeFase` e vira a área de gestão real do SEEG Ponto**: RH, gestor e diretoria autenticam, veem dashboards com KPIs e gráficos (incluindo uma estimativa de quem está com marcação em aberto hoje), cadastram e mantêm empresas, unidades (com geocerca em mapa), departamentos, centros de custo, cargos, equipes, colaboradores, contratos/vínculos, dispositivos e biometria, conferem e corrigem a apuração num grid mês × colaborador virtualizado que aguenta 500 colaboradores × 31 dias com fluidez, e montam/consultam escalas — tudo consumindo os endpoints reais já entregues por F1–F6 sob RBAC real, **sem que nenhuma tela edite marcação**.

**O que esta fase explicitamente não faz:** login/sessão do zero (esta fase **reusa** o módulo de sessão compartilhado que a F8 constrói — `apps/web/src/lib/sessao/**` —, nunca cria um segundo mecanismo; a rota `/` é ownership exclusivo da F8, não sua, ver §2), relatórios (`relatorios`, F11), fechamento e espelho oficial (`fechamentos`, `espelhos`, F10), workflow de aprovação de solicitações (`solicitacoes`, `aprovacoes`, F10), conformidade fiscal (`fiscal`, F12), webhooks (F13), administração de políticas/contas de banco de horas (nenhuma fase tem essa tela no escopo oficial hoje — ver §2, achado registrado), e nada do app mobile ou do portal do colaborador (`/eu`, F8). Se você está prestes a gerar um PDF de espelho ou implementar uma cadeia de aprovação, pare: não é desta fase.

## 2. Contexto mínimo

**O produto, em poucas frases.** SEEG Ponto é um REP-P (Registrador Eletrônico de Ponto via Programa, Portaria MTP 671/2021), SaaS multi-tenant. Cada cliente é um **tenant**, com suas empresas, unidades e pessoas, sob **Row Level Security** no PostgreSQL (você não vê nem toca nisso diretamente — é tudo aplicado pela API que você consome). Seis conceitos moldam toda tela desta fase: **marcação** (registro imutável de um instante, o REP-P não registra "entrada"/"saída" com certeza — o pareamento é feito na apuração); **tratamento** (a única forma legítima de corrigir a jornada, uma camada por cima da marcação que nunca a altera); **apuração** (resultado do cálculo de um dia para um vínculo: horas normais, extras, atrasos, faltas); **banco de horas** (conta-corrente de horas — **saldo credor**/**saldo devedor**, nunca "banco positivo/negativo"); **escala** (ciclo de trabalho — 5x2, 6x1, 4x2, 12x36, espanhola, rotativa — resolvido por aritmética modular a partir de uma data-âncora, sem materializar calendário); **vínculo** (a relação de trabalho — é nele que jornada, escala, apuração e conta de banco de horas penduram; a interface mostra o **colaborador**, mas o dado penduna no vínculo). Vocabulário obrigatório (glossário §6): **marcação** (nunca "batida"), **tratamento** (nunca "ajuste"/"correção de marcação"), **apuração** (nunca "cálculo"), **colaborador** (pessoa) / **vínculo** (relação) — nunca "funcionário", **saldo credor/devedor** (nunca "banco positivo/negativo"), **tenant** (nunca "empresa" para dizer cliente do SaaS), **coletor** (nunca "relógio de ponto"). Nenhum destes termos é reaberto por você — são decisões de `packages/contracts/glossario.md`, você só os usa corretamente.

**O que já existe e é FROZEN — leitura apenas.** `packages/contracts/**` está congelado desde a Fase 0. `apps/web/src/componentes/ui/**` e `apps/web/src/componentes/dominio/**` (mais `apps/web/src/componentes/graficos/**` e `apps/web/src/lib/formatacao/**`) são a entrega pronta da F9a: primitivos temáticos (botão, input, select, dialog, sheet, tabs, badge, tabela base, etc.), e os seis componentes de domínio — `LinhaDoTempoDeMarcacoes`, `CartaoDeSaldoDeBanco`, `GradeDeEscala`, `SeletorDePeriodo`, `TabelaDeDados` (virtualizada, com colunas configuráveis, ordenação e seleção) e `Graficos` (barras/linha/área/pizza com paleta acessível). **Você consome estes componentes por `import`, nunca copia o código nem cria um paralelo.** Precisou de uma variante que não existe? Isso é RFC/backlog, não invenção sua — mas antes de concluir que falta, leia o componente real (`apps/web/src/componentes/dominio/*.tsx`): as *props* costumam já cobrir mais do que parece.

**`apps/api`, `apps/worker` já implementam de verdade tudo que esta fase consome.** F1 (auth/RBAC/auditoria), F2 (organizacional/pessoas/biometria/dispositivos), F3 (jornadas/escalas/turnos), F4 (tratamentos/apurações/ocorrências/banco de horas), F5 (marcações/NSR), F6 (terminais Control iD) estão concluídas e verificadas contra banco real (commit `6350709` e anteriores). Nenhum endpoint que você chama responde mais `501` — se algum responder, é porque você chamou algo fora do que esta fase autoriza (ver §4 "Não toca").

**Achado bloqueante nº 1 — não existe sessão nem login em `apps/web`, e a solução já está decidida: você reusa o módulo da F8, não constrói um segundo.** `apps/web/src/app/page.tsx` (a rota `/`) é `PlaceholderDeFase` hoje, mas **a F8 (mesma onda, mesmo pacote de trabalho) constrói o login real ali** — formulário e-mail/senha/tenant, MFA, `accessToken` em memória, `refreshToken` em cookie `httpOnly` via três *Route Handlers* (`/api/auth/{login,refresh,logout}`) — porque é o mecanismo **mais seguro** disponível (o `refreshToken` nunca fica acessível a JavaScript de página, ao contrário de `sessionStorage`/`localStorage`, que qualquer *script* injetado por XSS conseguiria ler). **O orquestrador revisou os dois PCFs desta onda antes do build e decidiu: existe um único módulo de sessão no produto — `apps/web/src/lib/sessao/**`, ownership da F8 — e as duas áreas (`/eu` e `/painel`) o consomem.** Você **não** cria `apps/web/src/app/painel/entrar/page.tsx` nem `apps/web/src/lib/autenticacao/**` (versões anteriores deste PCF planejavam isso; foi corrigido). Em vez disso:

- `apps/web/src/app/painel/layout.tsx` (T1, A1) monta `<ProvedorDeSessao>` (import de
  `@/lib/sessao`, o mesmo componente que `/eu/layout.tsx` da F8 monta) e usa `useSessao()` —
  interface **fixada** (contrato entre as duas fases, não redecida por você):
  ```ts
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
  Sem `autenticado` e sem `carregando`, o *layout* redireciona para `/?returnTo=/painel` (nunca
  para uma rota `/painel/entrar`, que não existe mais) — a F8 já trata `returnTo` no formulário de
  `/` e navega de volta para `/painel` após login.
- `useSessao()` **não** inclui `permissoes`/`perfis` (são de `SessaoAtual`, `GET /v1/auth/sessao`)
  — isso é RBAC granular, que só esta fase precisa (§ próxima seção). Você faz sua própria
  `useQuery` chamando `obterSessaoAtual` por cima de `autenticado === true`; não precisa que a F8
  mude nada para isso funcionar, o cliente HTTP já manda `Authorization` assim que
  `definirProvedorDeToken` estiver ligado (feito pela F8, dentro do `ProvedorDeSessao` que você só
  monta).
- Se `apps/web/src/lib/sessao/**` ainda não existir no seu ambiente de build (a F8 roda em
  paralelo), programe contra a interface fixada acima como se já existisse — é exatamente o
  mesmo tipo de assinatura fixada entre agentes que a F4 usou (`verificar_periodo_aberto` entre A2
  e A3). Se a forma real divergir da fixada aqui quando a F8 terminar, é achado para o
  orquestrador reconciliar, não uma decisão sua a redecidir sozinho.

**RBAC no cliente: por permissão, nunca por nome de papel.** `GET /v1/auth/sessao` (`obterSessaoAtual`) devolve `SessaoAtual` com `perfis` (códigos de perfil) e **`permissoes`** (lista de códigos efetivos, já combinando perfis e negações — por exemplo `empresas.editar`, `apuracoes.executar`, `escalas.criar`). **Não existe no contrato um enum de "papel" (RH/gestor/diretoria)** — são rótulos de produto para agrupar telas nesta fase, não um campo de dado que a API exponha; os códigos de perfil reais são dado semeado por tenant (`apps/api/migrations/seed_dev.py`, fora do que você lê). Por isso: **toda tela e toda ação desta fase se habilita checando `sessao.permissoes.includes("<x-permissao exata do openapi.yaml>")`, nunca um `if perfil === "rh"`.** Um botão "excluir empresa" só aparece se `permissoes` contém `empresas.excluir`; uma seção do dashboard só aparece se `permissoes` contém a permissão do dado que ela mostra. Os recursos/ações relevantes desta fase (valor exato de `x-permissao`, confirme sempre contra o `openapi.yaml` antes de usar): `empresas.{ler,criar,editar,excluir}`, `unidades.{ler,criar,editar,excluir}`, `departamentos.{ler,criar,editar,excluir}`, `centros_custo.{ler,criar,editar}`, `cargos.{ler,criar,editar}`, `equipes.{ler,criar,editar}`, `colaboradores.{ler,criar,editar,excluir}`, `contratos.{ler,criar,editar}`, `vinculos.{ler,criar,editar}`, `dispositivos.{ler,criar,editar,excluir}`, `biometrias.{ler,criar,excluir,aprovar}`, `jornadas.{ler,editar}`, `escalas.{ler,criar,editar,excluir}`, `turnos.{ler,criar,editar}`, `tratamentos.{ler,criar,editar,excluir,aprovar}`, `apuracoes.{ler,executar}`, `ocorrencias.{ler,editar}`, `banco_horas.ler`, `marcacoes.ler`.

**Escopo hierárquico ("gestor vê sua árvore") é 100% aplicado pelo servidor — você nunca filtra por hierarquia no cliente.** A atribuição de perfil já carrega escopo (tenant, empresa, unidade, departamento, equipe ou próprio — glossário, verbete "Perfil e permissão"), e o servidor (`exigir_alcance`, F1) já devolve só o que o usuário pode ver em qualquer `GET` de lista. Se um gestor chama `GET /v1/colaboradores`, a resposta já vem recortada à árvore dele — você **não** reimplementa esse recorte, nem some/filtra registros no cliente "para garantir".

**Achado bloqueante nº 2 — `SessaoAtual.empresasVisiveis` está sempre `null` hoje.** É um gap já documentado (`docs/backlog.md`, linha de 2026-07-26, F1/A1): o campo existe no contrato mas a F1 nunca o preencheu para sessão humana (só faz sentido para cliente de integração OAuth). **Não espere por ele.** Para montar um seletor de empresa (RH multiempresa escolhendo qual empresa olhar), chame `GET /v1/empresas` diretamente — a listagem já vem recortada pelo RLS/RBAC do próprio tenant e escopo do usuário, exatamente como qualquer outra lista.

**"Tempo real de quem está trabalhando" — decisão de infraestrutura, fixada aqui.** Não existe WebSocket nem Server-Sent Events em nenhum lugar do repositório (`apps/api`, `apps/worker`, `apps/device-gw`) — confirmado por busca no código-fonte inteiro antes de escrever este PCF. **"Tempo real" nesta fase é *polling* via TanStack Query (`@tanstack/react-query`, já uma dependência instalada e já provida pela `ProvedorDeConsultas` em `apps/web/src/app/layout.tsx` — você não cria um novo `QueryClientProvider`), usando `refetchInterval` contra `GET /v1/marcacoes`.** Não use `GET /v1/apuracoes` para "hoje": apuração de um dia normalmente só é calculada no fechamento/recálculo (fim do dia ou depois), então o dia corrente tipicamente não tem `apuracoes_dia` ainda — a fonte viva é a marcação. `listarMarcacoes` aceita `empresaId`/`unidadeId` e `de`/`ate` (instante), então a consulta é `GET /v1/marcacoes?empresaId=...&de=<início do dia no fuso da unidade>&ate=<agora>&ordenar=datahoraMarcacao`, paginada por cursor. **Regra de domínio inegociável, a mesma que já rege `LinhaDoTempoDeMarcacoes` (releia o docstring do componente): o REP-P não registra entrada/saída com certeza, então este widget NUNCA afirma "colaborador X está trabalhando" como fato.** Ele conta, por vínculo, a paridade das marcações do dia (número ímpar de marcações = "ficou aberto") e exibe algo honesto como "última marcação às 14:32, sem marcação registrada depois" — nunca "trabalhando agora" como se fosse dado oficial. Isso é rótulo de apresentação (uma inferência de UX), não um novo campo oficial de sentido — não crie um campo `estaTrabalhando` em nenhum schema, é derivado só na tela.

**Mapa de geocerca — biblioteca a escolher, nenhuma instalada hoje.** Conferido em `apps/web/package.json`: não há `leaflet`, `mapbox-gl`, `maplibre-gl` nem equivalente. `Unidade`/`UnidadeCriar`/`UnidadeAtualizar` (`openapi.yaml`) definem geocerca **circular** (`geocercaLatitude`, `geocercaLongitude`, `geocercaRaioMetros`, graus decimais WGS84 e metros) **ou poligonal** (`geocercaPoligono`, GeoJSON `Polygon`/`MultiPolygon` — quando presente, tem precedência sobre a circular), mais `geocercaObrigatoria` e `geocercaToleranciaMetros`. **Escolha desta fase, documentada aqui e em `docs/backlog.md` para quem vier depois: `leaflet` + `react-leaflet`.** Motivo: é *open source*, não exige chave de API nem custo recorrente (ao contrário de Mapbox GL/Google Maps — relevante para um SaaS multi-tenant que não deveria repassar custo de mapa por tenant), e suporta nativamente tanto círculo (`L.circle`, raio em metros) quanto GeoJSON `Polygon`/`MultiPolygon` (`L.geoJSON`) — exatamente os dois formatos que o contrato já usa, sem tradução. Para permitir editar a geocerca no mapa (critério de aceite oficial), use um plugin de desenho (`leaflet-draw` ou equivalente) sobre a mesma biblioteca. **A versão exata fica para quem implementar**: confirme compatibilidade do `react-leaflet` com React 19 antes de fixar a versão no `package.json` (o ecossistema evolui rápido; se a versão estável mais recente não declarar suporte a React 19 como *peer dependency*, encapsule `leaflet` puro num componente cliente fino via `useEffect`+*ref*, sem `react-leaflet`, e registre a substituição em `docs/backlog.md`, mesmo padrão que a F9a já usou para o Storybook essentials). Tiles: use o servidor público do OpenStreetMap para desenvolvimento; hospedar um servidor de tiles próprio em produção é decisão de infraestrutura fora desta fase — registre em `docs/backlog.md` como pendência para F15.

**Achado de contrato nº 1 — não há leitura em lote de atribuições de escala.** `openapi.yaml`, tag `escalas`: existe `POST /v1/escalas/{escalaId}/atribuicoes` (`atribuirEscalaVinculo`), mas **não existe nenhum `GET`** equivalente (nem em `/v1/escalas/{escalaId}/atribuicoes`, nem em `/v1/vinculos/{vinculoId}/escalas` — este último, ao contrário de `/v1/vinculos/{vinculoId}/jornadas`/`listarJornadasVinculo`, simplesmente não existe). A única forma de saber "qual escala/turno vale para o vínculo X na data Y" é `GET /v1/jornadas/resolver` (`resolverJornadaDoDia`, um vínculo + uma data por chamada, devolve `escalaId`, `posicaoCiclo`, `turnoId`, `tipoDia`, `cargaPrevistaMinutos`, `feriadoId`, `afastamentoId` já resolvidos). Isso não bloqueia a fase (a operação existe e resolve tudo que uma célula da grade precisa), mas **força uma chamada por célula** em vez de uma leitura em lote. **Decisão fixada por este PCF (§6, T13):** a grade visual de escala desta fase é escopada à equipe do gestor logado (dezenas de vínculos, não milhares) e a um intervalo selecionado pelo `SeletorDePeriodo` (tipicamente um mês) — dentro desse recorte, N chamadas (`vínculos visíveis × dias visíveis`) com cache do TanStack Query por `(vinculoId, data)` é aceitável; **não é** a mesma exigência de fluidez de 500×31 que a grade de apuração tem (ver achado seguinte). Registre em `docs/backlog.md` a ausência de leitura em lote (`GET /v1/vinculos/{vinculoId}/escalas` análogo ao de jornadas, ou um `resolverJornadaEmLote`) como candidato a RFC para quem precisar de uma visão de escala no nível da empresa inteira.

**Achado de contrato nº 2 — "copiar período" não é uma operação, é composição.** Não há endpoint de cópia em `escalas` nem em nenhuma outra tag (busca confirmada no `openapi.yaml` inteiro). Como `Escala`/`EscalaAtribuicao` são desenhados para serem **perpétuos** (o ciclo se repete indefinidamente a partir de `dataReferencia`/`posicaoInicial`, "sem materializar calendário" — é o próprio texto do schema), uma atribuição vigente **já cobre os meses seguintes automaticamente**, sem precisar copiar nada, a menos que ela tenha `vigenciaFim` definida ou o gestor queira aplicar a mesma escala a um **novo grupo** de vínculos. "Copiar período" nesta fase é, portanto, composição no cliente: ler a posição de ciclo vigente de um vínculo de referência num dia da origem (`resolverJornadaDoDia` → `escalaId` + `posicaoCiclo`), e então criar a atribuição para os vínculos-alvo (`atribuirEscalaVinculo`) com a mesma `escalaId` e um `posicaoInicial` recalculado pela fórmula pública e documentada do próprio contrato (`Escala.diasCiclo`, `dataReferencia`) para a nova `vigenciaInicio` — **isto reproduz aritmética modular que o schema já expõe abertamente, não é duplicar a lógica de precedência escondida do resolvedor** (o que seria proibido). Não invente um endpoint `POST /v1/escalas/copiar`.

**Fora do escopo, mesmo parecendo próximo: administração de banco de horas.** `bh_politicas`/`bh_contas` (criar política, criar conta, tetos, regime) já têm API real (F4: `criarPoliticaBancoHoras`, `criarContaBancoHoras`, `listarPoliticasBancoHoras`, `listarContasBancoHoras`), mas **nenhuma fase do mapa oficial (`FASES-E-AGENTES.md`) tem, no escopo declarado, a tela de administração dessas duas entidades** — a lista oficial de telas de cadastro desta fase é "empresas, unidades, departamentos, centros de custo, cargos, colaboradores, contratos, dispositivos, biometria", sem banco de horas. Esta fase usa banco de horas só como **leitura** (`obterSaldoBancoHoras`, `obterExtratoBancoHoras`) dentro do dashboard e do cadastro de colaborador (via `CartaoDeSaldoDeBanco`, componente pronto da F9a). Não construa CRUD de política/conta de banco de horas aqui — registre em `docs/backlog.md` que essa tela não tem dono ainda.

**A vedação legal mais importante do projeto, já resumida em `apps/web/src/app/painel/page.tsx` (releia): nenhuma tela desta área edita marcação.** Toda correção de jornada é sempre um `tratamento` (`POST /v1/tratamentos`), auditado, numa camada separada. A regra é imposta em três lugares fora do seu controle (ausência de rota `PUT`/`PATCH`/`DELETE` em `marcacoes` no contrato, gatilho no banco, revogação de privilégio da role da aplicação) — você simplesmente nunca dá ao usuário um botão que sugira "editar marcação"; toda ação de correção no grid de apuração (A3) abre um formulário de tratamento.

**Critério de performance oficial:** a grade de apuração com 500 colaboradores × 31 dias (15.500 células) precisa navegar fluida (`FASES-E-AGENTES.md`, F9b). `TabelaDeDados` (`apps/web/src/componentes/dominio/tabela-de-dados.tsx`) já virtualiza com `@tanstack/react-virtual` — releia o arquivo real antes de montar a grade: ela recebe `linhas`/`colunas` genéricas (uma linha por **vínculo**, uma coluna por **dia** do intervalo escolhido, célula renderizada por `colunas[i].renderizarCelula`), tem `alturaContainerPx`/`alturaLinhaPx`, seleção controlável (para ações em lote) e ordenação. **Não renderize 15.500 células fora da virtualização "para simplificar" — é exatamente o padrão de uso que o componente já resolve.**

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia `PROJETO.md`, não leia o código de F1/F2/F3/F4/F5/F6, não releia `docs/fases/F09a-design-system.md` inteiro (só a tabela citada abaixo).

- `packages/contracts/openapi.yaml` — tags **completas**: `empresas`, `unidades` (inclui `/v1/unidades/{unidadeId}/redes-permitidas`), `organizacao` (departamentos, centros de custo, cargos, equipes), `colaboradores`, `contratos` (inclui `vinculos`), `biometria`, `dispositivos`, `escalas` (inclui `turnos`); **apenas as operações citadas** das tags `jornadas` (`listarJornadasVinculo`, `atribuirJornadaVinculo`, `resolverJornadaDoDia` — não leia `jornadas`/`horarios`/`feriados`/`afastamentos` inteiras, você só consome, não cadastra jornada nesta fase), `tratamentos` (as 7 operações), `apuracoes` (as 5, inclui `ocorrencias`), `banco-horas` (apenas `obterSaldoBancoHoras`, `obterExtratoBancoHoras`, `simularBancoHoras` — leitura/simulação; **não leia** `criarContaBancoHoras`/`criarPoliticaBancoHoras`/`criarQuitacaoBancoHoras`, fora de escopo), `marcacoes` (apenas `listarMarcacoes`, `obterMarcacao` — leitura), `auth` (apenas `autenticar`, `verificarSegundoFator`, `renovarSessao`, `encerrarSessao`, `obterSessaoAtual`). Leia também, em `components`: `parameters` (`CabecalhoTenant`, `CabecalhoRequestId`, `CabecalhoIdempotencia`, `Cursor`, `Limite`, `Ordenar`), `responses` (`Erro400`..`Erro503`), o schema `Problema`, e os schemas `Empresa*`, `Unidade*`, `RedePermitida*`, `Departamento*`, `CentroCusto*`, `Cargo*`, `Equipe*`, `EquipeMembro*`, `Colaborador*`, `Contrato*`, `Vinculo*`, `Dispositivo*`, `Biometria*`, `Escala*`, `EscalaCiclo`, `EscalaAtribuicao`, `Turno*`, `ResolucaoJornada`, `VinculoJornada*`, `Tratamento*`, `TipoTratamento*`, `ApuracaoDia`, `ListaApuracaoDia`, `ApuracaoComponente`, `Ocorrencia*`, `RecalculoRequisicao`, `ProcessamentoAssincrono`, `SaldoBancoHoras`, `ExtratoBancoHoras`, `Marcacao`, `ListaMarcacao`, `LoginRequisicao`, `LoginResposta`, `SessaoAtual`.
- `packages/contracts/errors.yaml` — categorias transversais **AUTH**, **PERM**, **TEN**, **VAL**, **CONF**, **REC**, **RATE**, **IDEM**, **INT** (toda tela pode encontrar qualquer uma), mais **APUR** (001–003), **BH** (todos), **PER** (001, 003) — específicos de apuração/banco de horas/fechamento, para você exibir a mensagem certa a partir de `Problema.codigo` (nunca de `title`/`detail`, que podem mudar sem quebrar contrato — mesma regra que `apps/web/src/lib/api/erros.ts` já documenta).
- `packages/contracts/glossario.md` — verbetes **Marcação**, **Tratamento**, **Apuração**, **Banco de horas**, **Crédito**, **Débito**, **Escala**, **Turno**, **Jornada**, **Vínculo**, **Colaborador**, **Geocerca**, **Allowlist CIDR**, **Perfil e permissão**, **Ocorrência**, **Período**, **NSR**, **Score de confiança**; seção **6 (Termos proibidos)** por inteiro.
- `docs/fases/F09a-design-system.md` — **apenas** a seção 4 ("Produz", tabela de componentes de domínio) e a seção 9 ("Proibições", para saber o que você não pode fazer com os tokens/componentes). Não releia o documento inteiro.
- `apps/web/src/app/eu/page.tsx` e `apps/web/src/app/painel/page.tsx` — leia os dois por inteiro. São o resumo oficial do escopo, já escrito pela F9a a partir de `FASES-E-AGENTES.md`.
- `docs/fases/F08-web-colaborador-webcam.md` — **apenas** a seção 2 (parágrafos sobre a interface fixada de `apps/web/src/lib/sessao/**` e o mecanismo `returnTo`) e a tarefa T1. Não leia o resto do PCF de F8 (webcam, prova de vida, allowlist não são seu assunto). Se `apps/web/src/lib/sessao/**` já existir quando você começar, leia o código real em vez de só a interface fixada aqui.
- `apps/web/src/componentes/andaime/placeholder-de-fase.tsx` e `cabecalho-do-andaime.tsx` — o segundo você edita minimamente (T1).
- `apps/web/src/componentes/dominio/**` (todos os `.tsx`, não só os `.stories.tsx`) — em especial `tabela-de-dados.tsx` (virtualização, *props* reais), `grade-de-escala.tsx`, `seletor-de-periodo.tsx`, `cartao-de-saldo-de-banco.tsx`, `linha-do-tempo-de-marcacoes.tsx`. `apps/web/src/componentes/ui/**` (primitivos disponíveis — não leia todos os `.stories.tsx`, só os componentes que for usar). `apps/web/src/componentes/graficos/graficos.tsx` e `paleta.ts`.
- `apps/web/src/lib/api/**` (`cliente.ts`, `config.ts`, `erros.ts`, `index.ts`, `tipos.gerado.ts`) e `apps/web/src/componentes/provedor-de-consultas.tsx` — o cliente HTTP tipado e o `QueryClient` já existem, você só usa.
- `apps/web/src/ganchos/use-estado-controlavel.ts` — padrão de estado controlável/não controlável já usado pelos componentes de domínio; reuse-o se algum componente seu precisar do mesmo padrão.
- `apps/web/src/app/layout.tsx` e `apps/web/src/app/page.tsx` (só para constatar que `/` é `PlaceholderDeFase` da F1 — você não o edita).
- `apps/web/package.json`, `apps/web/vitest.config.ts`, `apps/web/eslint.config.mjs`, `apps/web/tsconfig.json`, `apps/web/components.json`.
- `docs/rfc/README.md` e `docs/backlog.md` — procure "F9b" e "escala"/"tempo real"/"mapa" antes de começar.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- O design system inteiro da F9a (`apps/web/src/componentes/{ui,dominio,graficos}/**`, `apps/web/src/lib/formatacao/**`) — por `import`, nunca reescrito.
- O cliente HTTP tipado (`apps/web/src/lib/api/**`) e o `QueryClientProvider` (`apps/web/src/componentes/provedor-de-consultas.tsx`, já registrado em `apps/web/src/app/layout.tsx`).
- **`apps/web/src/lib/sessao/**` (F8, mesma onda)** — `ProvedorDeSessao` e `useSessao()`, interface fixada em §2. Você monta o *provider* e usa o *hook*; não edita o módulo nem cria um segundo. Se a F8 ainda não tiver terminado quando você começar, programe contra a interface fixada.
- Os 215 endpoints do `openapi.yaml`, implementados de verdade por F1–F6: em particular as tags `auth`, `empresas`, `unidades`, `organizacao`, `colaboradores`, `contratos`, `biometria`, `dispositivos`, `escalas` (inclui `turnos`), as operações citadas de `jornadas`, `tratamentos`, `apuracoes` (inclui `ocorrencias`), `banco-horas` (leitura) e `marcacoes` (leitura).
- O catálogo de permissões já semeado (F1) — você lê os códigos efetivos via `SessaoAtual.permissoes`, nunca semeia nem edita o catálogo.

**Produz** — esta fase implementa:

*Rotas (`apps/web/src/app/painel/**`, todas substituindo ou complementando o `PlaceholderDeFase` atual):*

| Rota | Agente | Conteúdo |
|---|---|---|
| `/painel` (índice) | A1 | Dashboards de RH/gestor/diretoria, KPIs, gráficos, "quem está com marcação em aberto hoje" |
| `/painel/cadastros/empresas`, `/unidades`, `/departamentos`, `/centros-custo`, `/cargos`, `/equipes`, `/colaboradores` (+ detalhe com contratos/vínculos/dispositivos/biometria) | A2 | CRUD conforme o contrato, mapa de geocerca em unidades |
| `/painel/apuracao` | A3 | Grade mês × colaborador, tratamento, ocorrências, recálculo |
| `/painel/escalas` | A4 | Cadastro de turnos/escalas, atribuição, grade visual, previsto × realizado |

*Componentes/hooks novos (não fazem parte do design system congelado — vivem em `apps/web/src/componentes/paineis/**` e `apps/web/src/ganchos/**`):* casca do painel e sessão (A1), formulários e mapa de cadastro (A2), grade e tratamento de apuração (A3), grade e formulários de escala (A4) — ver tabela de *ownership*, §5.

*Dependências novas em `apps/web/package.json`:* `leaflet`, `react-leaflet` (+ plugin de desenho de geocerca, ex. `leaflet-draw`), `@types/leaflet` (dev) — ver §2. Registre qualquer substituição em `docs/backlog.md`.

*Testes:* Vitest + Testing Library para lógica/render de componente; Playwright (já um devDependency, hoje só usado pelo *test-runner* do Storybook) ganha uso novo em `apps/web/playwright.config.ts` (novo arquivo) e `apps/web/e2e/**` para fluxos ponta a ponta contra API real.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- `apps/web/src/app/page.tsx` (rota `/`, login) e `apps/web/src/lib/sessao/**` — ownership da **F8**. Você monta `ProvedorDeSessao` e usa `useSessao()` (§2), nunca edita nem recria.
- `apps/web/src/app/eu/**`, `apps/web/src/app/api/auth/**` — portal do colaborador e *Route Handlers* de sessão, **F8**. Não construa nada ali.
- `apps/web/src/componentes/{ui,dominio,graficos}/**`, `apps/web/src/lib/formatacao/**`, `apps/web/src/componentes/tema/**`, `apps/web/src/estilos/tokens.gerado.css`, `apps/web/scripts/**`, `apps/web/src/lib/api/tipos.gerado.ts` — **congelados** (F0/F9a). Precisou mudar um desses? É RFC ou backlog, não edição direta.
- `packages/contracts/**` — **congelado**, sem exceção nesta fase (ao contrário da F4, esta fase não tem nenhuma alteração de contrato pré-aprovada).
- Tags `relatorios` (F11), `fechamentos`/`espelhos` (F10), `solicitacoes`/`aprovacoes` (F10), `fiscal` (F12), `webhooks` (F13) — endpoints ainda `501`; não chame esperando que funcionem.
- CRUD de `bh_politicas`/`bh_contas` (criação/edição de política e conta de banco de horas) — API existe (F4), mas nenhuma fase tem essa tela no escopo oficial; não invente aqui (achado registrado em §2).
- `apps/api/**`, `apps/worker/**`, `apps/device-gw/**`, `apps/facial-svc/**`, `apps/mobile/**`, `infra/**`, `.github/**` — outras fases/camadas.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase, e exclusivos por agente dentro dela.

| Agente | Caminhos |
|---|---|
| **A1** (casca, RBAC no cliente, dashboards) | `apps/web/src/app/painel/layout.tsx`<br>`apps/web/src/app/painel/page.tsx`<br>`apps/web/src/componentes/paineis/shell/**`<br>`apps/web/src/componentes/paineis/dashboard/**`<br>`apps/web/src/lib/permissoes/**` (novo)<br>`apps/web/src/ganchos/use-sessao-completa.ts` (novo — `useQuery` de `obterSessaoAtual` por cima de `useSessao()` da F8, ver §2)<br>`apps/web/src/ganchos/use-marcacoes-em-aberto.ts`<br>`apps/web/e2e/dashboard/**`<br>`apps/web/src/testes/paineis/shell/**`, `apps/web/src/testes/paineis/dashboard/**` |
| **A2** (cadastros) | `apps/web/src/app/painel/cadastros/**`<br>`apps/web/src/componentes/paineis/cadastros/**`<br>`apps/web/src/componentes/paineis/mapa/**`<br>`apps/web/src/ganchos/use-empresas.ts`, `use-unidades.ts`, `use-departamentos.ts`, `use-centros-custo.ts`, `use-cargos.ts`, `use-equipes.ts`, `use-colaboradores.ts`, `use-contratos.ts`, `use-vinculos.ts`, `use-dispositivos.ts`, `use-biometrias.ts`<br>`apps/web/e2e/cadastros/**`<br>`apps/web/src/testes/paineis/cadastros/**` |
| **A3** (grade de apuração) | `apps/web/src/app/painel/apuracao/**`<br>`apps/web/src/componentes/paineis/apuracao/**`<br>`apps/web/src/ganchos/use-apuracoes.ts`, `use-tratamentos.ts`, `use-ocorrencias.ts`, `use-recalculo.ts`<br>`apps/web/e2e/apuracao/**`<br>`apps/web/src/testes/paineis/apuracao/**` |
| **A4** (escalas) | `apps/web/src/app/painel/escalas/**`<br>`apps/web/src/componentes/paineis/escalas/**`<br>`apps/web/src/ganchos/use-escalas.ts`, `use-turnos.ts`, `use-resolucao-jornada.ts`<br>`apps/web/e2e/escalas/**`<br>`apps/web/src/testes/paineis/escalas/**` |

**Compartilhado dentro da fase** (exige combinação entre os agentes):

| Caminho | Regra |
|---|---|
| `apps/web/package.json` | Todos podem acrescentar dependência. **Só em ordem alfabética** dentro de `dependencies`/`devDependencies`, sem reordenar nem remover linha alheia. Scripts novos (ex. `test:e2e`) vão ao fim do bloco `scripts`. Combine quem roda `pnpm install` por último antes de fechar a fase — mesma regra que a F9a usou. |
| `apps/web/pnpm-lock.yaml` | Regenerado por `pnpm install`; conflito se resolve regenerando, nunca editando à mão. |
| `apps/web/src/componentes/andaime/cabecalho-do-andaime.tsx` | Só **A1** edita, e só a entrada `{ href: "/painel", ... }` do array `ROTAS` (remova o rótulo de fase "F9b" já que deixa de ser placeholder; **não** toque na entrada de `/` nem na de `/eu`). |
| `apps/web/playwright.config.ts` (novo) | Criado por **A1** na T1. Os demais agentes só acrescentam arquivos de teste nos seus próprios subdiretórios de `apps/web/e2e/**` — ninguém edita o arquivo de configuração depois de criado, a menos que combine com os outros três. |
| `apps/web/src/lib/permissoes/**` | Criado por **A1** (T1) — expõe um helper (`temPermissao(sessao, x)` e/ou um componente `<PortaoDePermissao permissao="...">`). A2/A3/A4 **consomem**, não editam; precisou de uma variante nova, pede a A1. |

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):

`packages/contracts/**`, `apps/web/src/componentes/ui/**`, `apps/web/src/componentes/dominio/**`, `apps/web/src/componentes/graficos/**`, `apps/web/src/lib/formatacao/**`, `apps/web/src/componentes/tema/**`, `apps/web/src/estilos/tokens.gerado.css`, `apps/web/scripts/**`, `apps/web/src/lib/api/tipos.gerado.ts`, `apps/web/src/lib/api/cliente.ts`/`config.ts`/`erros.ts`/`index.ts` (você usa, não edita — precisou de um comportamento novo no cliente HTTP, é achado de backlog), `apps/web/src/app/page.tsx`, `apps/web/src/app/eu/**`, `apps/web/src/app/layout.tsx`, `apps/web/src/componentes/provedor-de-consultas.tsx`, `apps/web/src/testes/andaime.teste.tsx`, `apps/web/next.config.ts`, `Dockerfile`, `postcss.config.mjs`, `apps/api/**`, `apps/worker/**`, `apps/device-gw/**`, `apps/facial-svc/**`, `apps/mobile/**`, `infra/**`, `.github/**`.

## 6. Tarefas (T1..T14)

### T1 — Casca do painel: reuso da sessão da F8 e RBAC no cliente
**Agente:** A1 — **primeira tarefa; A2/A3/A4 não escrevem nenhuma chamada à API antes desta task existir**
**Descrição:** **Você não constrói login nem armazenamento de token** (isso é `apps/web/src/lib/sessao/**`, ownership da F8, interface fixada em §2). `apps/web/src/app/painel/layout.tsx`: monta `<ProvedorDeSessao>` (import de `@/lib/sessao`) envolvendo o conteúdo de `/painel`, usa `useSessao()` para decidir a guarda de rota — sem `autenticado` e sem `carregando`, redireciona para `/?returnTo=/painel` (nunca renderiza uma tela de gestão sem sessão). `apps/web/src/ganchos/use-sessao-completa.ts`: `useQuery` (TanStack Query) chamando `obterSessaoAtual` (`GET /v1/auth/sessao`) condicionado a `useSessao().autenticado === true`, cacheado, exposto como `{ sessao, carregando, erro }` — é aqui, e só aqui nesta fase, que `permissoes`/`perfis` aparecem. `apps/web/src/lib/permissoes/**`: `temPermissao(sessao, permissao: string): boolean` e um componente `<PortaoDePermissao permissao="...">{children}</PortaoDePermissao>` que só renderiza os filhos quando `sessao.permissoes.includes(permissao)`. Editar `apps/web/src/componentes/andaime/cabecalho-do-andaime.tsx` (só a entrada `/painel`, ver §5). Criar `apps/web/playwright.config.ts` apontando para `pnpm dev` como servidor local.
**Pronto quando:** acessar `/painel` sem sessão redireciona para `/?returnTo=/painel`; login nessa URL (credencial de desenvolvimento, semeada por `apps/api/migrations/seed_dev.py`, contra API real subida localmente) volta para `/painel` autenticado (prova de que o mecanismo de `returnTo` da F8 funciona de ponta a ponta com este *layout*); logout/token expirado redireciona de volta pelo mesmo caminho; `temPermissao` tem teste unitário cobrindo presente/ausente; nenhum arquivo novo em `apps/web/src/lib/autenticacao/**` nem `apps/web/src/app/painel/entrar/**` existe (a busca por esses caminhos não encontra nada — prova de que você não recriou o que é da F8); `pnpm exec playwright test e2e/dashboard` (ou equivalente mínimo desta task) prova o fluxo ponta a ponta contra a API real.

### T2 — Dashboards de RH, gestor e diretoria
**Agente:** A1
**Descrição:** `apps/web/src/app/painel/page.tsx` e `apps/web/src/componentes/paineis/dashboard/**`: KPIs e gráficos (`Graficos`, componente pronto da F9a) compostos a partir de `GET /v1/apuracoes` (agregado por período — extras, faltas, atrasos, ocorrências abertas por severidade), `GET /v1/ocorrencias` (fila de inconsistências), `GET /v1/colaboradores` (contagem por status/departamento), `obterSaldoBancoHoras`/`CartaoDeSaldoDeBanco` (amostra ou agregado, conforme o que a permissão do usuário alcançar). **Cada seção do dashboard é individualmente controlada por `<PortaoDePermissao>`** (T1) com a permissão exata do dado que ela mostra (ex. seção de custo/banco de horas exige `banco_horas.ler`; seção de cadastro/empresas exige `empresas.ler`) — **não existe um `if papel === "rh"`** em lugar nenhum do código. Empresa/unidade selecionável via `GET /v1/empresas`/`GET /v1/unidades` (nunca via `SessaoAtual.empresasVisiveis`, que está sempre `null` — achado documentado em §2).
**Pronto quando:** dashboard renderiza com dados reais de uma API local subida (não *mock*); seção cujo dado a sessão atual não tem permissão de ler simplesmente não aparece (prova por teste: sessão sem `banco_horas.ler` não renderiza o cartão de saldo); dois temas (claro/escuro) sem quebra visual; responsivo até 1280 px (critério oficial de aceite).

### T3 — "Quem está com marcação em aberto" (tempo real por polling)
**Agente:** A1
**Descrição:** `apps/web/src/ganchos/use-marcacoes-em-aberto.ts`: `useQuery` com `refetchInterval` (30–60 s) contra `GET /v1/marcacoes` (filtros `empresaId`/`unidadeId`, `de`=início do dia no fuso da unidade, `ate`=agora), agrupa por `vinculoId`, calcula paridade (`ímpar` = provável em aberto) e a última marcação. Widget no dashboard (A1) usando `LinhaDoTempoDeMarcacoes`/rótulo textual honesto — **nunca** "está trabalhando" como fato; sempre "última marcação às HH:MM" + rótulo de inferência.
**Pronto quando:** teste unitário prova a paridade (par → não listado; ímpar → listado com o horário da última marcação); nenhum texto do componente afirma presença como certeza (grep no código-fonte do componente não encontra "está trabalhando" nem equivalente categórico); widget atualiza sozinho dentro do intervalo de *polling* configurado, comprovado por teste com temporizador simulado (`vi.useFakeTimers`).

### T4 — Cadastro de empresas e unidades
**Agente:** A2
**Descrição:** `apps/web/src/app/painel/cadastros/empresas/**`: lista (`listarEmpresas`, `TabelaDeDados`), criar/editar/excluir (`criarEmpresa`/`atualizarEmpresa`/`excluirEmpresa`) via formulário com primitivos da F9a. `apps/web/src/app/painel/cadastros/unidades/**`: lista e formulário (`listarUnidades`/`criarUnidade`/`atualizarUnidade`/`excluirUnidade`), incluindo os campos de fuso e allowlist CIDR (`listarRedesPermitidas`/`criarRedePermitida`/`excluirRedePermitida` — sub-recurso do mesmo formulário, aba ou seção "Redes permitidas"). O campo de geocerca fica para T5 (não bloqueia o resto do formulário).
**Pronto quando:** CRUD completo das duas telas conforme o contrato; cada ação (criar/editar/excluir) só aparece com a permissão correspondente (`empresas.criar`/`editar`/`excluir`, `unidades.*`); erro de conflito (`PONTO-CONF-*`, `409`) exibido a partir de `Problema.codigo`.

### T5 — Mapa de geocerca
**Agente:** A2
**Descrição:** `apps/web/src/componentes/paineis/mapa/**`: componente `MapaDeGeocerca` sobre `leaflet`/`react-leaflet` (ou o encapsulamento fino decidido em §2), recebendo/emitindo os campos do contrato (`geocercaLatitude`/`Longitude`/`RaioMetros` **ou** `geocercaPoligono` GeoJSON — polígono tem precedência), com modo de edição (arrastar centro/raio do círculo, desenhar/editar vértices do polígono) integrado ao formulário de unidade (T4). Verifique que o mapa nunca produz um `z-index` que sobreponha um `Dialog`/`Toast` do design system — a escala `camada` do contrato tem `dialogo=900`, acima de qualquer *pane* padrão do Leaflet; se precisar sobrepor manualmente, nunca escreva um valor literal, use `var(--camada-...)`.
**Pronto quando:** criar/editar unidade com geocerca circular e com geocerca poligonal (GeoJSON) grava e recarrega corretamente contra API real; editar no mapa reflete no formulário e vice-versa; teste E2E (Playwright) desenha uma geocerca circular e confirma o valor salvo via `GET /v1/unidades/{id}`; nenhum literal de cor/espaçamento/`z-index` do design system é sobrescrito por CSS do Leaflet fora do necessário para o mapa em si.

### T6 — Departamentos, centros de custo, cargos, equipes
**Agente:** A2
**Descrição:** Quatro telas sob `apps/web/src/app/painel/cadastros/{departamentos,centros-custo,cargos,equipes}/**`, mesmo padrão de lista + formulário. **Atenção às operações realmente disponíveis** (confira o `openapi.yaml`, não assuma): `departamentos` tem CRUD completo (`listar`/`criar`/`obter`/`atualizar`/`excluir`); `centros-custo` e `cargos` **não têm operação de exclusão** (só `listar`/`criar`/`obter`/`atualizar` — o formulário não oferece um botão "excluir" para essas duas entidades, use o campo `ativo` via `atualizar` para desativar); `equipes` tem `listar`/`criar`/`obter`/`atualizar` mais `adicionarMembroEquipe` (**não há remoção de membro no contrato** — não ofereça essa ação, é achado de backlog se for necessária).
**Pronto quando:** as quatro telas cobrem exatamente as operações que existem (nenhum botão aponta para uma operação inexistente); teste prova que a tela de centro de custo/cargo não expõe ação de exclusão.

### T7 — Colaboradores, contratos e vínculos
**Agente:** A2
**Descrição:** `apps/web/src/app/painel/cadastros/colaboradores/**`: lista (`listarColaboradores`, filtros por empresa/unidade/departamento/status/gestor), criar/editar/excluir (`criarColaborador`/`atualizarColaborador`/`excluirColaborador`), gestão de gestores (`listarGestoresColaborador`/`definirGestoresColaborador`), importação (`importarColaboradores`, reaproveita o fluxo assíncrono já usado por outras importações do projeto — `ProcessamentoAssincrono`). Detalhe do colaborador com abas/seções para contratos (`listarContratos`/`criarContrato`/`atualizarContrato` — **sem exclusão**, mesma observação da T6) e vínculos (`listarVinculos`/`criarVinculo`/`obterVinculo`/`encerrarVinculo` — **não há `atualizarVinculo`**, só criação e encerramento; para mudar um dado do vínculo que não seja "encerrar", não existe operação, é achado de backlog).
**Pronto quando:** CRUD de colaborador completo; detalhe mostra contratos e vínculos reais do colaborador; nenhum botão de "editar vínculo" genérico é oferecido (só "encerrar"); importação em lote mostra o estado do processamento assíncrono até concluir.

### T8 — Dispositivos e biometria
**Agente:** A2
**Descrição:** `apps/web/src/app/painel/cadastros/dispositivos/**`: CRUD (`listarDispositivos`/`criarDispositivo`/`atualizarDispositivo`/`excluirDispositivo`/`vincularDispositivo`). `apps/web/src/app/painel/cadastros/.../biometria` (aba do colaborador, não tela própria): **apenas administração de matrículas já existentes** — listar (`listarBiometrias`), revogar (`revogarBiometria`), aprovar/validar (`validarBiometria`). **Esta fase não captura biometria nova via câmera** (isso depende de `getUserMedia`/app móvel, escopo de F7/F8, ambas fora desta fase) — a tela só mostra o que já foi enviado por outro canal e permite revogar/aprovar.
**Pronto quando:** lista de dispositivos e de biometrias do colaborador reflete a API real; revogar/aprovar biometria funciona e atualiza a lista; nenhum componente desta tela usa `getUserMedia` ou qualquer captura de câmera.

### T9 — Grade de apuração (virtualizada)
**Agente:** A3
**Descrição:** `apps/web/src/app/painel/apuracao/**`: `SeletorDePeriodo` (F9a) para escolher o intervalo, filtros (empresa/unidade/departamento/equipe/colaborador — todos suportados por `GET /v1/apuracoes`), e `TabelaDeDados` (F9a, virtualizada) com **uma linha por vínculo e uma coluna por dia** do intervalo, célula colorida/rotulada por `tipoDia`/`status`/presença de ocorrência (nunca só por cor — WCAG 1.4.1, mesma regra que a F9a já impôs aos componentes de domínio). Chame `GET /v1/apuracoes` com `de`/`ate` obrigatórios, `incluirComponentes=false` por padrão (o parâmetro existe mas "aumenta bastante o volume da resposta" — só ative sob demanda, ex. ao abrir o detalhe de uma célula). Destaque de inconsistência usa `somenteInconsistentes` e os campos de `Ocorrencia.severidade`/`codigo`.
**Pronto quando:** *benchmark* com 500 vínculos × 31 dias (dado sintético ou paginado da API real) prova que o DOM mantém a virtualização (menos de 100 linhas simultâneas, mesmo padrão que a F9a provou para a `TabelaDeDados` com 10.000 linhas) e que a montagem/rolagem não trava (métrica registrada no relatório); célula com ocorrência aberta é visualmente distinguível por cor **e** por rótulo/ícone.

### T10 — Tratamento a partir da grade (nunca marcação)
**Agente:** A3
**Descrição:** `apps/web/src/componentes/paineis/apuracao/**`: ao clicar numa célula, abre um `Dialog` (F9a) com o detalhe do dia (marcações do dia via `LinhaDoTempoDeMarcacoes`, componentes da apuração) e um formulário de **tratamento** (`criarTratamento`/`atualizarTratamento`/`cancelarTratamento`/`decidirTratamento`, tag `tratamentos`) — categorias conforme `listarTiposTratamento`. **Nenhum controle desta tela chama, sugere ou nomeia "editar marcação"** — o rótulo de toda ação de correção é sempre "tratamento". Lista de ocorrências (`listarOcorrencias`/`atualizarOcorrencia`) acessível a partir da mesma tela, referenciando o `tratamentoId` quando resolvida por tratamento.
**Pronto quando:** criar um tratamento a partir da grade e aprová-lo reflete a apuração recalculada (evento `apuracao.recalculada` observado indiretamente por refetch); teste de varredura do código-fonte confirma que nenhum texto visível na tela usa "editar marcação"/"corrigir marcação"/"batida"; `cancelarTratamento` nunca apaga a linha original (a UI mostra o tratamento cancelado como histórico, não remove da lista).

### T11 — Recálculo sob demanda e ações em lote
**Agente:** A3
**Descrição:** Botão "Recalcular" no escopo selecionado (vínculo/empresa/unidade/departamento + intervalo), chamando `POST /v1/apuracoes/recalcular` (`RecalculoRequisicao`) — resposta é `202` com `ProcessamentoAssincrono` (`status: enfileirado`). **Não existe operação de consulta de status por identificador** (achado já documentado pela F4, `docs/backlog.md`) — a UI não faz *polling* de um endpoint que não existe; em vez disso, mostra "recálculo solicitado" e deixa o usuário atualizar a grade manualmente ou via *refetch* do TanStack Query após um intervalo curto, e reflete o resultado assim que `GET /v1/apuracoes` mudar (mesma fonte de verdade da T9). Ações em lote na grade (seleção múltipla via `TabelaDeDados`, F9a) permitem disparar o mesmo recálculo para os vínculos selecionados.
**Pronto quando:** disparar recálculo mostra estado "enfileirado" imediatamente e não trava a UI; a grade eventualmente reflete o novo resultado após o *refetch*; nenhum código tenta chamar um endpoint de status de recálculo inexistente.

### T12 — Turnos, escalas e atribuição
**Agente:** A4
**Descrição:** `apps/web/src/app/painel/escalas/**` (seção de cadastro): turnos (`listarTurnos`/`criarTurno`/`atualizarTurno` — **sem exclusão nem `obterTurno` individual**; para exibir o detalhe de um turno, use o item já carregado pela listagem, não invente uma chamada), escalas (`listarEscalas`/`criarEscala`/`obterEscala`/`atualizarEscala`/`excluirEscala`, com o editor dos `ciclos` — `EscalaCiclo[]`, uma posição por linha: `turnoId`, `tipoDia`, `cargaMinutos`), e atribuição a vínculo (`atribuirEscalaVinculo`, `POST /v1/escalas/{escalaId}/atribuicoes`).
**Pronto quando:** criar uma escala 12x36 (dois `ciclos`: trabalho 720 min / folga) e atribuí-la a um vínculo funciona contra API real; teste prova que a tela não tenta exibir/editar um turno por um `GET` individual inexistente.

### T13 — Grade visual de escala, previsto × realizado e cobertura por turno
**Agente:** A4
**Descrição:** `apps/web/src/componentes/paineis/escalas/**`: grade visual usando `GradeDeEscala` (F9a) para o período selecionado (`SeletorDePeriodo`) e a equipe do gestor logado — célula por `(vinculo, dia)` resolvida via `resolverJornadaDoDia` (achado de contrato nº 1, §2: sem leitura em lote, uma chamada por célula, cacheada por `(vinculoId, data)`, escopo limitado à equipe/período visíveis). "Previsto × realizado": para dias **já apurados** (passado/atual, `status` diferente de futuro), prefira `GET /v1/apuracoes` (já traz `previstoMinutos` **e** `trabalhadoMinutos` na mesma chamada, sem N+1); para dias **futuros** (ainda sem apuração), use só o previsto de `resolverJornadaDoDia` (`cargaPrevistaMinutos`). "Cobertura por turno": agregação client-side das células já resolvidas (contagem de vínculos por `turnoId` por dia). "Copiar período": composição descrita em §2 (achado de contrato nº 2) — ler a posição de ciclo de referência via `resolverJornadaDoDia`, recalcular `posicaoInicial` pela aritmética modular pública do próprio schema (`diasCiclo`, `dataReferencia`), e chamar `atribuirEscalaVinculo` por vínculo-alvo.
**Pronto quando:** grade visual renderiza turno por célula com cor e rótulo (nunca só cor); "previsto × realizado" usa `GET /v1/apuracoes` para dias já apurados (prova por teste: nenhuma chamada a `resolverJornadaDoDia` é feita para uma data com apuração já disponível) e `resolverJornadaDoDia` só para datas futuras; "copiar período" aplicado a um grupo de vínculos produz as atribuições esperadas, verificável contra `resolverJornadaDoDia` no período destino.

### T14 — Fechamento
**Agentes:** A1, A2, A3 e A4
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório da fase, item a item contra a §7.
**Pronto quando:** todos verdes, com saída colada; `git status --short packages/contracts` vazio; `git status --short apps/web/src/componentes/ui apps/web/src/componentes/dominio apps/web/src/componentes/graficos apps/web/src/lib/formatacao` vazio (design system intocado).

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **Grade de apuração com 500 colaboradores × 31 dias navega fluida**: DOM virtualizado (menos de 100 linhas simultâneas), tempo de montagem/rolagem registrado no relatório (critério oficial, `FASES-E-AGENTES.md`, F9b).
2. **Toda edição gera tratamento auditado e nunca altera marcação**: nenhuma tela chama, sugere ou nomeia "editar marcação"; toda correção passa por `POST`/`PATCH`/`DELETE /v1/tratamentos*` (critério oficial).
3. **Geocerca editável em mapa e refletida no app**: criar/editar geocerca circular e poligonal no mapa grava e recarrega corretamente contra `GET`/`PATCH /v1/unidades/{id}` (critério oficial).
4. **Dois temas e responsivo até 1280 px** em todas as telas novas (critério oficial).
5. **RBAC por permissão, nunca por papel hardcoded**: toda ação/seção condicionada a `sessao.permissoes.includes(x-permissao exata)`; nenhum `if perfil === "..."` no código-fonte (verificável por busca).
6. **"Tempo real" implementado por *polling*, honestamente rotulado**: nenhum texto afirma presença como fato; nenhuma tentativa de WebSocket/SSE inexistente no código.
7. **Sessão reusada, não recriada**: `/painel` reusa `ProvedorDeSessao`/`useSessao()` de `apps/web/src/lib/sessao/**` (F8); acesso sem sessão redireciona para `/?returnTo=/painel`, que autentica contra `POST /v1/auth/login` real e volta para `/painel`; não existe `apps/web/src/app/painel/entrar/**` nem `apps/web/src/lib/autenticacao/**`; `apps/web/src/app/page.tsx` e `apps/web/src/lib/sessao/**` (F8) permanecem intocados por esta fase.
8. **Todas as telas de cadastro usam exatamente as operações que existem no contrato**: nenhum botão aponta para `excluirCentroCusto`/`excluirCargo`/`atualizarVinculo`/`obterTurno`/`excluirTurno`/qualquer operação inexistente (ver §2/§6).
9. **Contrato intacto**: `git status --short packages/contracts` vazio.
10. **Design system intocado**: `git status --short` vazio para `apps/web/src/componentes/{ui,dominio,graficos}` e `apps/web/src/lib/formatacao`.
11. **`pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` verdes**, incluindo `src/testes/andaime.teste.tsx` (não pode quebrar).
12. **`pnpm tokens:check` e `pnpm tipos:api:check` verdes** (ninguém editou artefato gerado).
13. **E2E ponta a ponta contra API real** (`pnpm exec playwright test`) cobre, no mínimo: login, um CRUD de cadastro completo, um ciclo de tratamento na grade de apuração, e uma atribuição de escala.
14. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir de `apps/web`, salvo onde indicado. Os alvos equivalentes na raiz são `make lint-web`/`test-web`/`typecheck` e `.\tasks.ps1 lint-web`/`test-web`/`typecheck`.

Instalar dependências (depois que os 4 agentes tiverem acrescentado as suas em `package.json`):

```bash
pnpm install
```

Tokens e tipos da API sincronizados (ninguém editou artefato gerado):

```bash
pnpm tokens:check
pnpm tipos:api:check
```

**Saída esperada:** sucesso, sem diferença apontada.

Lint, tipos, testes e build:

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

**Saída esperada:** ESLint sem erro; `tsc --noEmit` sem erro; Vitest com todos os testes passando, **incluindo** `src/testes/andaime.teste.tsx`; `next build` concluindo.

Subir a stack real para os testes E2E (mesmo padrão de infraestrutura que as fases de backend já usam):

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis api worker
cd apps/api && alembic upgrade head && python migrations/seed_dev.py
```

```powershell
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis api worker
cd apps/api; alembic upgrade head; python migrations/seed_dev.py
```

E2E ponta a ponta (Playwright, contra a API real subida acima):

```bash
cd apps/web && pnpm exec playwright install --with-deps chromium
pnpm dev &
pnpm exec playwright test
```

**Saída esperada:** todos os cenários (login, um CRUD de cadastro, um ciclo de tratamento, uma atribuição de escala) passam, em ambos os temas onde aplicável; nenhuma violação `serious`/`critical` de `axe-playwright` nas telas novas.

Benchmark da grade de apuração (500 × 31), com o tempo impresso:

```bash
pnpm vitest run src/testes/paineis/apuracao/grade-de-apuracao.desempenho.teste.tsx --reporter=verbose
```

**Saída esperada:** menos de 100 linhas no DOM para 15.500 células e tempo de montagem/rolagem registrado, com o valor real impresso.

Contrato e design system intocados (a partir da raiz do repositório):

```bash
git status --short packages/contracts
git status --short apps/web/src/componentes/ui apps/web/src/componentes/dominio apps/web/src/componentes/graficos apps/web/src/lib/formatacao
```

**Saída esperada:** nada em ambos.

## 9. Proibições

1. **Não edite `packages/contracts/`** — esta fase não tem nenhuma exceção pré-aprovada (diferente da F4). Achou o contrato incompleto? É RFC, formato de `docs/rfc/README.md`.
2. **Não edite `apps/web/src/componentes/{ui,dominio,graficos}/**` nem `apps/web/src/lib/formatacao/**`** — congelados pela F9a. Precisou de uma variante nova, é RFC/backlog, não edição direta nem componente paralelo duplicado em `paineis/`.
3. **Não toque em `apps/web/src/app/page.tsx`** (rota `/`, login real da F8), **nem em `apps/web/src/lib/sessao/**`** (módulo de sessão, ownership da F8), **nem em `apps/web/src/app/eu/**`** (portal do colaborador, F8). **Não crie `apps/web/src/app/painel/entrar/**` nem `apps/web/src/lib/autenticacao/**`** — esta fase reusa o login e a sessão da F8 (§2), nunca recria um segundo mecanismo.
4. **Não implemente nenhuma tela nem chamada para as tags `relatorios`, `fechamentos`, `espelhos`, `solicitacoes`, `aprovacoes`, `fiscal`, `webhooks`** — todas ainda `501` ou de outra fase. Se uma tela "parece precisar" de relatório, é F11: registre em `docs/backlog.md`.
5. **Não construa CRUD de `bh_politicas`/`bh_contas`** (criação/edição de política ou conta de banco de horas) — API existe, mas não há tela dona no escopo oficial; use banco de horas só como leitura (saldo/extrato).
6. **Não invente endpoint que não existe no contrato** — em particular: não crie um "copiar período" ou "resolver em lote" no backend (é composição no cliente, §2/§6); não chame `excluirCentroCusto`, `excluirCargo`, `atualizarVinculo`, `obterTurno`, `excluirTurno`, `removerMembroEquipe` — nenhum existe.
7. **Não implemente WebSocket/SSE nem qualquer infraestrutura de tempo real nova** — não existe hoje em nenhuma camada do backend; "tempo real" é *polling* via TanStack Query, ponto final.
8. **Não filtre por hierarquia/escopo no cliente** ("gestor vê sua árvore" já é aplicado pelo servidor) e **não hardcode nome de papel** (`"rh"`/`"gestor"`/`"diretoria"`) em nenhuma condicional — gate sempre por `sessao.permissoes.includes(x-permissao exata)`.
9. **Não use os termos proibidos** da seção 6 do glossário: é *marcação* (nunca "batida"), *tratamento* (nunca "editar"/"corrigir marcação"), *apuração* (nunca "cálculo"), *colaborador*/*vínculo* (nunca "funcionário"), *saldo credor/devedor* (nunca "banco positivo/negativo"), *tenant* (nunca "empresa" para dizer cliente do SaaS).
10. **Não capture biometria nova via câmera** (`getUserMedia` ou equivalente) — é F7/F8. A tela de biometria desta fase só administra o que já existe (listar/revogar/aprovar).
11. **Não implemente armazenamento de token nem formulário de senha nesta fase** — `accessToken`/`refreshToken` são geridos inteiramente por `apps/web/src/lib/sessao/**` (F8); você só monta `<ProvedorDeSessao>` e lê `useSessao()`. Se estiver escrevendo `localStorage.setItem`/`sessionStorage.setItem` com um token ou senha, pare — não é desta fase.
12. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real** — em especial o *benchmark* da grade de apuração e os testes E2E contra API real, não contra *mock*.
