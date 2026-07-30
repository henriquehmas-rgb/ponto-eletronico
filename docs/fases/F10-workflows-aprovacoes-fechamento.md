# F10 — Workflows, aprovações e fechamento

| | |
|---|---|
| **Onda** | 4 |
| **Agentes** | 4 · **A1** motor de solicitações (tipos configuráveis, cadeia de aprovação gestor→RH, prazos, escalonamento, delegação, histórico) · **A2** fechamento (conferência, correções, trava, geração do espelho, assinatura eletrônica do colaborador, reabertura auditada e nominal) · **A3** notificações multicanal (push, e‑mail, in‑app; motor de regras; preferência por usuário; arquitetura pronta para WhatsApp/OpaSuite, sem implementá‑lo) · **A4** férias, afastamentos e abonos (solicitação, programação, aprovação, efeito no cálculo, anexos, tipos configuráveis) |
| **Duração estimada** | 8 dias |
| **Depende de** | F4 (cálculo e banco de horas, concluída, commit `6350709`) e F9b (painel RH e gestor, concluída, commit `a3f5af5`) — ambas já verificadas contra banco real |
| **Criticidade** | Alta — F11 (relatórios/espelho) e F12 (AFD/AEJ) dependem do resultado desta fase para fechamento, espelho e trilha de aprovação |
| **Branch** | `f10-workflows-aprovacoes-fechamento` |

---

## 1. Objetivo

Ao fim desta fase, uma solicitação aberta pelo colaborador ou pelo gestor **percorre a cadeia de
aprovação configurada** (gestor → RH, com prazo, escalonamento e delegação), e sua aprovação final
**materializa automaticamente** o tratamento, o afastamento ou a quitação de banco de horas
correspondente — refletindo na apuração sem jamais tocar a marcação; um período pode ser
**conferido, fechado (travando a edição), reaberto apenas de forma nominal e justificada**, e gera
**espelhos de ponto com assinatura eletrônica do colaborador verificável e não repudiável**; e as
regras de notificação (esqueceu de bater, jornada excedida, banco vencendo, pendência há N dias)
disparam mensagens reais nos canais push, e‑mail e in‑app — enquanto as operações das tags
`solicitacoes`, `aprovacoes`, `fechamentos`, `espelhos` deixam de responder `501` e passam a
implementar o workflow completo descrito em `PROJETO.md` §6.

**O que esta fase explicitamente não faz:** cálculo de apuração e banco de horas (F4, concluída — esta
fase **reaproveita**, nunca duplica); telas do painel RH/gestor (F9b, concluída — só o backend novo
desta fase, nenhum arquivo de `apps/web`); relatórios e exportação em PDF com "layout de designer"
(F11); AFD/AEJ/assinatura CAdES do REP‑P (F12); envio real por WhatsApp via OpaSuite (decisão do dono
do produto, ver §2); entrega de webhook (F13). Se você está prestes a recalcular horas, editar uma
tela React, desenhar um PDF bonito ou chamar a API do OpaSuite, pare: não é desta fase.

## 2. Contexto mínimo

**O produto.** Sistema de ponto eletrônico brasileiro **REP‑P** (Portaria MTP 671/2021), SaaS
multi‑tenant. Toda tabela desta fase carrega `tenant_id` sob **Row Level Security**; a aplicação abre
cada transação publicando `app.tenant_id` (`apps/api/app/db/sessao.py::obter_sessao`, real, F1). Você
não desabilita RLS.

**A sequência canônica do motor, estendida por esta fase** (`packages/contracts/glossario.md` §5 mais
o elo que só existe a partir daqui):

```
solicitação (esta fase, A1 — tipos configuráveis, cadeia gestor→RH, prazo, escalonamento, delegação)
      ↓ aprovação final da cadeia
materialização (esta fase, A1 para ajuste/abono/justificativa/compensação/afastamento retroativo
                 via reaproveitamento de tratamento; A4 para férias/folga — Afastamento/banco de horas)
      ↓
tratamento aprovado (F4, já implementado — a ÚNICA forma legítima de corrigir jornada)
      ↓
apuração do dia (F4, já implementada)
      ↓
lançamentos de banco de horas (F4, já implementado)
      ↓
fechamento de período (esta fase, A2 — conferência → trava → espelho → assinatura)
      ↓
espelho de ponto oficial + assinatura eletrônica do colaborador (esta fase, A2)
```

A seta nunca aponta para trás: esta fase não recalcula nada, não escreve em `apuracoes_dia` nem em
`bh_lancamentos`, e não reescreve o que a F4 já resolveu. Ela **produz o insumo** (tratamento aprovado,
afastamento aprovado, quitação) que a F4 **consome**, e **consome o resultado** (apuração fechada) que
ela trava e assina.

### 2.1 A fronteira exata com F4 — o que já existe, o que você adiciona

Releia `docs/fases/F04-calculo-banco-de-horas.md` §2 e §9 (proibição 4) antes de escrever qualquer
linha. **Confirmado lendo `apps/api/app/apuracao/tratamento/servico.py` e `decisao.py` na íntegra
(somente leitura — ownership congelado de F4, você não edita nenhum dos dois arquivos):**

- `tratamentos.solicitacao_id` já existe como FK de referência (`ALTER TABLE tratamentos ADD
  CONSTRAINT fk_tratamentos_solicitacao FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes (id) ON
  DELETE SET NULL`, `schema.sql` linha 3171‑3173) e o código de F4 já a usa: `criar_tratamento`,
  `atualizar_tratamento`, `cancelar_tratamento` e `decidir_tratamento` **já compilam e já são
  testados** contra um `Tratamento` com `solicitacao_id` preenchido.
- `app/apuracao/tratamento/decisao.py::decidir_tratamento(sessao, tenant_id, tratamento_id, dados:
  DecisaoRequisicao, *, usuario_id) -> Tratamento` **já publica `ajuste.aprovado`/`ajuste.reprovado`
  automaticamente quando `tratamento.solicitacao_id is not None`** (via `app.apuracao.tratamento.
  eventos.publicar_ajuste_aprovado/reprovado`, que já busca a `Solicitacao` pelo id e usa
  `solicitacao.protocolo` no payload) e **já agenda o recálculo do dia** (`recalcular_periodo`,
  intervalo `data_referencia ± 1 dia`). F4 construiu esse mecanismo **exatamente para esta fase
  reaproveitar** — releia o comentário em `servico.py` linha 5‑10: "`tratamentos` é a ÚNICA forma de
  corrigir a jornada... um tratamento referencia uma marcação existente apenas por `marcacao_id`" e em
  `decisao.py` linha 3‑16: "`decidirTratamento` é a aprovação **do tratamento**, nunca a aprovação da
  `solicitacao_id` referenciada (o workflow de aprovação de solicitações em si é da F10)".
- **O que F4 não fez, e é o núcleo desta fase:** a cadeia de aprovação em si (tabelas `solicitacoes`,
  `aprovacoes`, `delegacoes`, `tipos_solicitacao` — todas já existem no schema desde a Fase 0, F4 só as
  referenciou), o roteamento por etapa/papel, prazo, escalonamento, e o código que **cria** o
  `Tratamento` (ou o `Afastamento`, ou a `BhQuitacao`) a partir de uma solicitação aprovada.

**Decisão fixada por este PCF, para você não reinventar o que F4 já entregou:** quando a etapa final da
cadeia de uma solicitação aprova e a categoria mapeia para um `tipo_tratamento_id` (ver §2.2), você
**cria** o `Tratamento` em `status='pendente'` referenciando `solicitacao_id` e **chama
`app.apuracao.tratamento.decisao.decidir_tratamento(sessao, tenant_id, tratamento.id,
esquemas.DecisaoRequisicao(decisao="aprovar", comentario=...), usuario_id=aprovador_usuario_id)`** —
reaproveitando aprovação, recálculo e publicação de `ajuste.aprovado` já implementados e testados por
F4, sem duplicar uma linha de lógica. **Leia a assinatura real do módulo antes de chamar** (ele é
código de outra fase, só leitura); se a assinatura não bastar, é RFC, não um contorno.

### 2.2 Achado empírico: como cada categoria de solicitação materializa (fonte: `seed_dev.py`, Fase 0)

`apps/api/migrations/seed_dev.py::TIPOS_SOLICITACAO` (linhas 469‑560+, **você não edita este
arquivo**, é dado de fábrica já semeado pela Fase 0) já fixa, tupla a tupla, o mapeamento entre
`categoria` da solicitação e o `codigo` do `tipo_tratamento` associado (último campo da tupla, `str |
None`). Isto não é uma decisão sua — é o dado real já gravado, e você o lê, nunca o redecide:

| `categoria` (`tipos_solicitacao`) | Etapas (papel) | `tipo_tratamento` associado | O que a aprovação final materializa |
|---|---|---|---|
| `ajuste_ponto` | gestor → rh | `inclusao_manual` | `Tratamento` (via `decidir_tratamento`, §2.1) |
| `abono` | gestor → rh | `abono_falta` | `Tratamento` (idem) |
| `justificativa` | gestor | `justificativa_atraso` | `Tratamento` (idem) |
| `compensacao` | gestor | `compensacao` | `Tratamento` (idem) |
| `afastamento` | rh | `afastamento_retroativo` | `Tratamento` com `tipo_afastamento_id` preenchido (idem) — **não** cria linha em `afastamentos`; é uma correção retroativa de um dia **já apurado**, o mesmo padrão de qualquer outro tratamento (ver `tratamentos.tipo_afastamento_id`, `schema.sql`) |
| `ferias` | gestor → rh | **nenhum** (`None`) | `Afastamento` novo, criado por **A4** (§2.3) — data futura, ainda não apurada, não precisa de tratamento/recálculo |
| `folga` | gestor | **nenhum** (`None`) | Consumo de banco de horas, materializado por **A4** chamando o serviço já implementado de F4 (`app.apuracao.banco_horas.quitacoes`, §2.3) |
| `troca_escala` | gestor | **nenhum** (`None`) | **Nenhuma materialização automática nesta fase** — decisão fixada abaixo |
| (demais categorias do enum sem tipo configurado por padrão: `hora_extra`, `desbloqueio_dispositivo`, `outro`) | conforme o tenant configurar | depende do tenant | Regra genérica: **se** `tipos_solicitacao.tipo_tratamento_id` estiver preenchido (o tenant pode configurar um tipo próprio via `criarTipoSolicitacao`), materializa `Tratamento`; **senão**, só marca `aprovada`/`resultado`, sem efeito automático |

**Decisão fixada:** para qualquer categoria **sem** `tipo_tratamento_id` e **fora** de
`{ferias, folga}`, a aprovação final só transiciona `solicitacoes.status` para `aprovada` e preenche
`resultado`/`concluida_em` — nenhum efeito automático é inventado (troca de escala é domínio de F9b/
escalas, fora do escopo desta fase; se isso se provar insuficiente em produção, registre em
`docs/backlog.md`, não invente uma tabela ou side‑effect novo).

**A distinção "afastamento" (tratamento retroativo) vs. "ferias"/"folga" (sem tratamento) não é
arbitrária:** é a distinção entre corrigir um dia **já apurado no passado** (o tratamento existe
exatamente para isso, e o "retroativo" no nome do tipo de tratamento de fábrica confirma) e programar
uma ausência **futura, ainda não apurada** (o resolvedor da F3 já lê `afastamentos.status='aprovado'`
como insumo normal — nenhum recálculo retroativo é necessário porque o dia nunca foi apurado sem essa
informação).

### 2.3 Ownership da materialização dentro da fase (evita conflito de arquivo entre A1 e A4)

- **A1** possui o **despachante genérico**: ao aprovar a última etapa, resolve `tipos_solicitacao.
  tipo_tratamento_id`; se preenchido, cria o `Tratamento` e chama `decidir_tratamento` (§2.1) — isto
  cobre `ajuste_ponto`, `abono`, `justificativa`, `compensacao`, `afastamento` (retroativo) e qualquer
  categoria que o tenant configure com um tipo de tratamento próprio. Você escreve isto **uma vez**,
  de forma genérica — não é "código do abono", é "código de qualquer categoria com tratamento".
- **A4** possui o **ramo `ferias`/`folga`** do mesmo despachante: um módulo próprio
  (`app/workflow/solicitacoes/afastamentos.py`, ownership exclusivo de A4, §5) que A1 **importa e
  chama** quando a categoria é `ferias` ou `folga` — mesmo padrão de fronteira interna que F4 usou
  entre A1/A2/A3 (funções com assinatura fixada, nunca duplicadas). Combine a assinatura exata com A1
  antes de escrever (sugestão de forma, não obrigatória: `async def materializar_ferias_ou_folga
  (sessao, tenant_id, solicitacao, *, aprovador_usuario_id) -> None`).
- Nenhuma outra combinação existe: se você (A1 ou A4) achar que uma categoria precisa de um terceiro
  ramo, é achado de contrato — documente em `docs/backlog.md`, não invente um quarto caminho.

**Para `ferias`:** resolva `tipo_afastamento_id` consultando `tipos_afastamento WHERE tenant_id = ?
AND categoria = 'ferias' AND ativo = true` (a categoria `ferias` já existe no `CHECK` de
`tipos_afastamento.categoria`, `schema.sql` linha ~1754). Se nenhum ou mais de um tipo ativo for
encontrado, é erro de configuração do tenant (`PONTO-REC-001` se nenhum; se isso importar para o
critério de aceite, trate como validação de negócio — não invente código de erro novo). Crie
`Afastamento(status='aprovado', origem='solicitacao', solicitacao_id=solicitacao.id, data_inicio=
solicitacao.data_inicio, data_fim=solicitacao.data_fim, tipo_afastamento_id=..., vinculo_id=
solicitacao.vinculo_id, colaborador_id=solicitacao.colaborador_id, aprovado_por=aprovador_usuario_id,
aprovado_em=agora)`. **Antes de inserir, verifique `ex_afastamentos_sobreposicao`** (a `EXCLUDE
CONSTRAINT` já existe no banco e recusa dois afastamentos integrais aprovados sobrepostos) — trate a
violação com uma mensagem de negócio clara, não deixe vazar o erro cru do Postgres.

**Para `folga`:** o efeito é consumir banco de horas, não criar afastamento. Chame o serviço **já
implementado e testado por F4** em `app.apuracao.banco_horas.quitacoes` (leia o módulo real antes de
usar — o nome exato da função e sua assinatura não foram declarados como "produzidos para outras
fases" no PCF de F4, então confirme lendo o código, do mesmo jeito que você confirmaria qualquer outro
módulo já implementado; se a forma não servir, é RFC, você não duplica a lógica de consumo FIFO/LIFO
nem a de validação de saldo). Isto é reaproveitamento de código de F4, não escrita em `bh_lancamentos`
por fora do mecanismo de F4.

### 2.4 A assinatura eletrônica do espelho — decisão fixada, e por que não é a assinatura da F12

**Não confunda as duas assinaturas do sistema.** A F12 assina o **AFD/AEJ** (arquivo fiscal oficial)
com **CAdES `.p7s` e certificado ICP‑Brasil e‑CNPJ da empresa** — isso é prova de autoria da SEEG
perante o Ministério do Trabalho, e não existe nesta fase (nem o certificado está disponível ainda,
`FASES-E-AGENTES.md` F12). **Esta fase assina o espelho de ponto com o aceite do colaborador** —
prova de que ELE tomou ciência da jornada apurada, mecanismo completamente diferente e mais simples.

O mecanismo **já está fixado no schema, não é uma decisão em aberto**: `assinaturas_espelho.metodo`
tem `DEFAULT 'aceite_eletronico'` e o comentário da própria coluna diz "`aceite_eletronico` com
carimbo de tempo e hash é o padrão. `icp_brasil` é usado quando o cliente exige certificado"
(`schema.sql` linha 3134‑3135, 3153). O enum `metodo` aceita `icp_brasil`/`biometria`/`senha`/
`token_email` para o dia em que um cliente exigir mais — **você implementa apenas `aceite_eletronico`
nesta fase**; os demais métodos ficam com o valor aceito no `CHECK` mas sem implementação (mesmo
padrão de "contrato mais amplo que a implementação atual" que F4 já viu em `banco_horas`/
`bh_politicas`). Se o critério de aceite pedir explicitamente `icp_brasil` no futuro, é fase nova, não
esta.

**A fórmula de verificabilidade e não repúdio, fixada por este PCF** (decisão de lógica de aplicação,
não de contrato — não abre RFC):

1. No momento do aceite, o colaborador já está vendo `Espelho.conteudo` (o snapshot JSON congelado) e
   `Espelho.hashSha256` (calculado na geração do espelho, §2.5). O cliente envia de volta o
   `hashSha256` que ele viu (`AssinaturaEspelhoRequisicao.hashSha256`) — **o servidor recusa o aceite
   se esse valor não bater byte a byte com o `espelhos.hash_sha256` gravado** (evita assinar uma versão
   que já mudou entre a exibição e o clique).
2. `assinaturas_espelho.hash_assinado` grava exatamente esse hash (redundante com `espelhos.
   hash_sha256` de propósito: a linha de assinatura fica **autocontida e verificável mesmo se o
   espelho fosse hipoteticamente reemitido** — não é o caso normal, mas a tabela é append‑only e a
   verificação não deveria depender de outra tabela mudar de estado).
3. `carimbo_tempo` é o relógio do servidor no momento do INSERT (nunca o relógio do cliente); `ip` e
   `user_agent` vêm da requisição HTTP (mesmo padrão de captura que `aprovacoes.ip` já usa). Isto é o
   "não repúdio": autor, quando, de onde, o quê exatamente ele viu.
4. **Imutabilidade real, não só disciplina de código:** `assinaturas_espelho` já tem os dois gatilhos
   `trg_assinaturas_espelho_bloqueia_update`/`_delete` (`fn_registro_imutavel`, mesmo padrão de
   `marcacoes`/`bh_lancamentos`) — uma vez gravada, a linha não muda nunca. Escreva o teste que
   confirma isso com a role de aplicação real (não superusuário), mesmo padrão de evidência que F4
   exigiu para `bh_lancamentos`.
5. **`espelhos` NÃO tem gatilho de imutabilidade** (confirmado lendo o schema — só `assinaturas_
   espelho` tem `trg_..._bloqueia_update/delete`; `espelhos` não). A imutabilidade de um espelho já
   assinado é **disciplina de aplicação**, não do banco: uma vez que existe **qualquer**
   `assinaturas_espelho.status='assinado'` para um `espelho_id`, seu código **nunca** executa `UPDATE`
   nessa linha de `espelhos` — uma retificação sempre cria `Espelho` novo com `versao` incrementada
   (`uq_espelhos_versao` já impede duas linhas com a mesma versão) e `tipo='retificado'`. Escreva o
   teste que prova isto (tentar "corrigir" um espelho assinado deve resultar em uma nova versão, nunca
   em alteração da antiga) — é o comportamento que a reabertura de período depende (§2.6).
6. **Verificação = recomputação, não um endpoint novo.** "Verificável" significa: qualquer parte
   (auditoria interna, o próprio colaborador, um perito) pode recalcular `SHA256(json_canonico
   (espelho.conteudo))` e confirmar que bate com `espelho.hash_sha256` **e** com `assinatura.
   hash_assinado`. Use a MESMA canonicalização já usada por `app.identidade.auditoria.hash_chain.
   _json_canonico` (`json.dumps(valor, sort_keys=True, separators=(",", ":"), default=str)`) — reaproveite
   o padrão, não invente uma segunda forma de canonicalizar JSON no sistema. **Não é** um hash
   encadeado como o de `auditoria`/`marcacoes`/`bh_lancamentos` (não há "hash anterior" entre
   assinaturas — cada uma é independente, ligada só ao espelho que assina); não implemente uma cadeia
   aqui, seria over-engineering fora do que o schema pede.

### 2.5 Geração do espelho — o que é desta fase e o que é da F11

O `Espelho` (JSON + hash + totais) **é desta fase** — é o documento que trava no fechamento e que o
colaborador assina, tag `espelhos` do contrato, agente A2. `EspelhoCriar.gerarPdf`/`GET /v1/espelhos/
{espelhoId}/pdf` (`baixarEspelhoPdf`) também são operações desta tag e **você implementa um PDF real**,
não um stub — o critério de aceite oficial ("assinatura do colaborador é verificável") pressupõe que
existe algo concreto para o colaborador ler antes de assinar.

**Fronteira exata com F11 (`FASES-E-AGENTES.md`, F11/A4: "Espelho de ponto oficial em PDF, cabeçalho
legal, layout de designer, agendamento por e‑mail"):** você entrega um PDF **funcionalmente completo e
juridicamente correto** (todos os campos exigidos pela Portaria 671/2021 para o espelho, cabeçalho
com identificação da empresa/período/colaborador, corpo com os dias e totais, rodapé com hash e dados
da assinatura quando houver) usando uma biblioteca de geração de PDF simples (ex.: `reportlab` ou
`weasyprint` a partir de um template HTML — escolha e documente, adicione a dependência ao `pyproject.
toml` do `apps/api`), **sem** investir em identidade visual refinada, tipografia de marca ou layout
customizável — isso é explicitamente o que a F11 refina depois ("layout de designer"), sobre os
**mesmos dados** (`Espelho.conteudo`/`hashSha256`), sem mudar o contrato. Não vale a pena captar tempo
desta fase em polimento visual que a F11 vai substituir.

**Storage: primeira integração real com MinIO no código da aplicação.** `infra/.env.example` já
provisiona o MinIO (`MINIO_ROOT_USER`, `MINIO_BUCKET=ponto`, comentário explícito "objetos: fotos de
captura, **anexos**, **PDFs**, AFD/AEJ e `.p7s`", linha 119) mas **nenhum código de `apps/api`/`apps/
worker` fala com ele ainda** (confirmado: nenhuma dependência de SDK de objeto — `boto3`, `minio` — em
qualquer `pyproject.toml` até esta fase). Você é quem cria essa integração pela primeira vez: adicione
a dependência (`minio` ou `boto3`, sua escolha — documente o motivo), um módulo pequeno de acesso
(`app/comum/armazenamento.py` ou equivalente, ownership de A2 já que é quem primeiro precisa, mas
reaproveitável por A4 se precisar armazenar atestado, §6) com `salvar_objeto`/`obter_url_assinada`
sobre as variáveis já existentes (`MINIO_*` de `infra/.env.example`, leia `app/core/config.py` para o
padrão de configuração já usado por outras variáveis de ambiente). `Espelho.conteudo_ref` grava a
chave do objeto (não a URL completa — mesmo padrão que o comentário do schema já documenta:
"`conteudo_ref`: Chave do PDF no MinIO").

### 2.6 Fechamento, trava e reabertura — reaproveitando o hash chain de auditoria (F1)

**"Fechar período trava edição"** significa: com um `Fechamento.status='fechado'` cobrindo a data e o
escopo (empresa/unidade/departamento/equipe/colaborador), qualquer tentativa de criar/atualizar
tratamento, decidir tratamento, recalcular ou lançar quitação naquele dia responde `PONTO-PER-001` —
**este mecanismo já existe e já está implementado por F4** (`app/apuracao/tratamento/fechamento.py::
verificar_periodo_aberto`, chamado por `criarTratamento`, `decidirTratamento`, `recalcularApuracoes`, e
pela A2 de F4 em `criarQuitacaoBancoHoras`). **Você não reimplementa essa trava** — ela já dispara
sozinha assim que existir uma linha de `fechamentos` com `status='fechado'` cobrindo a data; o seu
trabalho é **criar essa linha** (a operação `criarFechamento`) da forma correta, e nada mais.

**"Reabrir exige justificativa registrada com autor"** — o `CHECK` `ck_fechamentos_reabertura`
(`schema.sql` linha 3073‑3075) já impede fisicamente reabrir sem `motivo_reabertura`/`reaberto_por`
preenchidos. **Para a trilha auditável, reaproveite `app.identidade.auditoria.hash_chain.
gravar_auditoria`** (F1, real e testado — mesma função que F4 já reaproveitou para o diff de
recálculo): `entidade="fechamentos"`, `acao="reabrir"` (já aceito pelo `CHECK` de `auditoria.acao` —
`'fechar'` e `'reabrir'` e `'assinar'` já estão na lista de valores permitidos, `schema.sql` linha
3559‑3561, **nenhuma migration nova necessária para isto**), `entidade_id=fechamento.id`,
`usuario_id=quem_reabriu`, `valor_anterior={"status": "fechado"}`, `valor_novo={"status": "reaberto",
"motivo": ...}`, `metadados={"dataInicio": ..., "dataFim": ...}` quando a reabertura for parcial. Não
reescreva a lógica de hash chain — ela já existe e está certa (leia a docstring completa do módulo, é
a fórmula fixa do hash e o mecanismo de lock por advisory lock).

**Não crie uma segunda trilha de auditoria para o workflow.** `aprovacoes`/`solicitacoes` já carregam
seu próprio histórico granular nas próprias colunas (`decidido_em`, `aprovador_usuario_id`,
`aprovador_delegacao_id`, `ip`) — isso não substitui `gravar_auditoria`, que você ainda chama para
toda decisão de aprovação/fechamento/reabertura/assinatura (mesmo padrão que F4 usou para
`tratamento.cancelado`), mas não invente uma tabela de log paralela.

### 2.7 Achados de contrato — documentados aqui, não corrigidos silenciosamente

Estes quatro achados foram confirmados lendo `packages/contracts/openapi.yaml` por inteiro nas tags
relevantes. Nenhum deles bloqueia esta fase (você implementa em volta, do jeito descrito), mas **não
invente uma correção silenciosa** — se um deles se tornar bloqueante para o seu trabalho específico,
pare a tarefa afetada e abra RFC (`docs/rfc/README.md`); caso contrário, registre em
`docs/backlog.md` com a fase sugerida indicada abaixo.

1. **Não existe tag/endpoint `notificacoes` no `openapi.yaml`.** A tabela `notificacoes` e
   `notificacao_preferencias` existem desde a Fase 0 (`schema.sql` seção 11), e o catálogo de
   permissões já semeou `workflow.notificacoes` com ações `ler`/`criar`
   (`apps/api/migrations/seed_dev.py` linha 178) — mas **nenhuma operação HTTP** usa essas permissões
   em lugar nenhum do contrato (confirmado: `grep -c "^  /v1/notificacoes" openapi.yaml` = 0). Isto
   significa que **o canal in‑app não tem uma rota própria de "listar minhas notificações"/"marcar como
   lida" nesta fase**. Decisão fixada: você constrói o **motor** completo (grava linhas reais em
   `notificacoes`, populadas corretamente, com `lida_em` nula) e o consumo in‑app fica pronto para o
   dia em que o endpoint existir — **não invente `GET /v1/notificacoes`** por conta própria (seria
   adicionar operação ao contrato sem RFC, proibido). Registre este achado em `docs/backlog.md` como
   candidato a RFC (fase sugerida: quem primeiro precisar da tela de sino de notificações — F9b já
   está pronta, então provavelmente uma micro‑fase ou a própria F11). O e2e do critério de aceite
   "notificação chega... in‑app" é satisfeito **verificando a linha em `notificacoes` com
   `canal='in_app'` e `status` avançando de `pendente` para `enviada`**, não por uma chamada HTTP de
   leitura que não existe.
2. **Não existe tag/endpoint `anexos` nem `documentos` no `openapi.yaml`** (confirmado da mesma forma:
   zero ocorrências de `/v1/anexos` ou `/v1/documentos`). Isto é uma lacuna **pré‑existente e
   sistêmica**, não introduzida por esta fase: `AfastamentoCriar`/`ContratoCriar`/`BiometriaCriar` (F2,
   F3 — já concluídas) já têm campos `documentoId` opcionais que **nenhuma fase até agora conseguiu
   popular via API**, porque não existe operação de upload. **Você não resolve isto nesta fase** — é
   maior que o seu escopo e nenhuma fase anterior tentou. Trate `documentoId`/anexo de atestado como
   um campo opaco que o cliente só consegue preencher se já tiver um `documentos.id` de outra origem
   (hoje, nenhuma). Registre em `docs/backlog.md` (acrescentando a este achado pré‑existente, não
   duplicando) — não invente `/v1/anexos` nem grave arquivo direto em `anexos`/`documentos` a partir
   de uma rota desta fase sem um contrato HTTP que a autorize.
3. **`ProcessamentoAssincrono.tipo` não tem o valor `fechamento`** no enum (`recalculo`, `afd`, `aej`,
   `relatorio`, `importacao`, `exportacao_folha`, `espelho`, `sincronizacao_terminal` — sem
   `fechamento`; `espelho` já existe e serve para `gerarEspelhos`). Precedente idêntico já decidido:
   **RFC‑010** adicionou `sincronizacao_terminal` a este mesmo enum quando a F6 encontrou a mesma
   lacuna. `tipo` **não é campo obrigatório** no schema (`ProcessamentoAssincrono` não declara
   `required`, confirme lendo o schema) — decisão fixada: `criarFechamento` devolve
   `ProcessamentoAssincrono` **sem preencher `tipo`** (válido pelo schema) até que uma RFC nova
   acrescente o valor. Se você quiser abrir essa RFC (mesmo formato da RFC‑010), é bem‑vindo, mas não
   é bloqueante — implemente sem o campo.
4. **`ajuste.aprovado.payload.tratamentoId` é `required` em `events.yaml` (linha 331:
   `required: [solicitacaoId, protocolo, colaboradorId, dataReferencia, tratamentoId, decididoEm]`),
   mas as categorias `ferias`/`folga` (§2.2‑2.3) nunca produzem um `Tratamento`** — não há
   `tratamentoId` nenhum para preencher. Isto é uma inconsistência real do contrato (o evento foi
   desenhado pensando só no caminho "solicitação → tratamento", antes de `ferias`/`folga` existirem
   como categorias com efeito próprio). **Decisão fixada, para A4 não reinventar:** para `ferias`/
   `folga`, publique `ajuste.aprovado` com `tratamentoId` **ausente do dicionário `dados`** (o
   `BARRAMENTO_INTERNO` interno de cada domínio, usado só para prova por teste e depuração local, não
   valida o payload contra o JSON Schema de `events.yaml` em tempo de execução — confirme lendo
   `app/apuracao/tratamento/eventos.py`, que já publica variações opcionais da mesma forma) e
   **registre esta divergência em `docs/backlog.md` como candidato a RFC** (tornar `tratamentoId`
   opcional, ou acrescentar um campo alternativo `afastamentoId`/`quitacaoId` ao payload — a decisão é
   do orquestrador, não sua). O teste do critério de aceite 11 ("eventos batem campo a campo") cobre
   os campos que **existem**; documente esta exceção pontual no próprio teste, não a esconda.
5. **`ajuste.solicitado` só é declarado para a categoria `ajuste_ponto`** (`events.yaml`, "quando
   dispara: Na criação de uma solicitação cujo tipo pertence à categoria `ajustePonto`"). Isto é
   literal do contrato, não uma escolha sua: `criarSolicitacao` publica `ajuste.solicitado` **apenas**
   quando `tipos_solicitacao.categoria == 'ajuste_ponto'`; para as demais categorias (`ferias`,
   `abono`, `folga`, `afastamento`, ...), **nenhum evento de criação é publicado** — a próxima
   observação do estado é via `ajuste.aprovado`/`ajuste.reprovado` na conclusão, ou via `GET /v1/
   solicitacoes`. Não amplie o evento para outras categorias "porque faria mais sentido" — é RFC se
   você achar que o contrato está errado.

**O bus de eventos ainda não é real entre domínios — implicação direta para A3.** Cada domínio já
implementado (F2, F3, F4, F5) publica em um `BARRAMENTO_INTERNO: list[dict]` **isolado por módulo**
(confirme lendo `app/apuracao/tratamento/eventos.py` linha 30‑33: "só para prova por teste e depuração
local — a **F13** substitui por fila de verdade sem mudar a assinatura de `publicar`"). F13 (Onda 5,
depois desta) ainda não existe. Isto significa que **você não consegue "escutar" eventos de outro
domínio já concluído** (`ocorrencia.aberta` de F4, `banco_horas.vencendo` de F4, `terminal.offline` de
F6, `marcacao.*` de F5) sem editar o arquivo `eventos.py` daquele domínio — proibido, é ownership de
fase já concluída. **Decisão fixada, ver §6 T9‑T11:** o motor de notificações desta fase tem dois
caminhos de disparo, nunca um "barramento genérico":

- **Reativo, só para os eventos que ESTA fase publica** (`ajuste.solicitado`, `ajuste.aprovado`,
  `ajuste.reprovado`, `periodo.fechado`, `periodo.reaberto`, `espelho.assinado`) — o próprio código de
  A1/A2/A4 chama o motor de notificações **em processo**, logo após publicar o envelope, no mesmo
  módulo que ele já possui (nenhum arquivo de outra fase é tocado).
- **Por varredura periódica (polling), para sinais que nascem em domínios já concluídos** (ocorrência
  `jornada_excedida`/`sem_marcacao` de F4, `banco_horas.vencendo`/ocorrência `banco_vencendo` de F4) —
  uma rotina nova de `scheduler` (A3, §6 T11) lê diretamente as tabelas `ocorrencias`/`solicitacoes`/
  `aprovacoes` (leitura simples, sem ownership envolvido — ler tabela de outro domínio é normal neste
  sistema, F4 já lê `jornadas`/`marcacoes` de F3/F5) e usa a coluna `notificacoes.entidade`/
  `entidade_id` já existente no schema para não notificar duas vezes o mesmo evento (idempotência por
  "já existe uma notificação para esta entidade+canal", não por marca de estado numa tabela nova).

### 2.8 Push e e‑mail — nenhum provedor real configurado ainda (mesmo tratamento do WhatsApp)

Confirmado em `infra/.env.example`: **não existe nenhuma variável de SMTP, FCM (Firebase Cloud
Messaging) ou APNs no arquivo inteiro** (grep por `SMTP_`, `FCM_`, `APNS_`, `EMAIL_` — zero ocorrências
fora deste achado). `apps/mobile` existe como diretório mas é o esqueleto vazio da Fase 0 — **F7 (app
Flutter) não foi executada** (confirmado pela memória do projeto: Onda 3 completa exceto F7,
"Flutter indisponível"), então não há SDK de push integrado em lugar nenhum do repositório.

**Decisão do dono do produto, já fixada — não redecida:** o canal **WhatsApp via OpaSuite** (citado em
`PROJETO.md` §6 e `FASES-E-AGENTES.md` F10) fica **explicitamente fora do escopo desta fase**. Não há
credencial/API disponível ainda; é adiamento deliberado, não esquecimento. Você constrói a
**arquitetura completa** de notificação (fila `notificacoes`, motor de regras, formato de mensagem,
preferência por usuário/canal/janela de silêncio, e a **coluna `notificacoes.provedor`**, que já aceita
livremente o valor `"opasuite"` — é `TEXT` sem `CHECK`, confirme lendo o schema — sem que isso implique
implementá‑lo) de forma que plugar o canal seja **só escrever uma função de envio nova depois**
(`app/notificacao/canais/whatsapp.py`, ownership futuro, arquivo que você **não cria** nesta fase). O
mesmo raciocínio, pelo mesmo motivo (nenhuma credencial real disponível), se aplica a **push (FCM/
APNs)** e **e‑mail (SMTP)**: implemente `app/notificacao/canais/push.py` e `.../email.py` com a
**interface completa** (assinatura de função, tratamento de erro, retentativa, atualização de
`notificacoes.status`/`enviada_em`/`erro`) mas com o **envio real substituído por um adaptador "log +
grava como enviada"** claramente documentado como provisório — nunca uma chamada HTTP inventada para
um provedor sem credencial. O critério de aceite "notificação chega nos canais reais (push/e‑mail/
in‑app) em teste e2e" (que **não inclui WhatsApp**, ver acima) é satisfeito **provando que a linha de
`notificacoes` é criada corretamente, o adaptador de canal é chamado com o payload certo, e o `status`
avança para `enviada`** — não por uma caixa de entrada real recebendo o e‑mail, já que não há SMTP
configurado. Se o time de produto fornecer credencial de SMTP/FCM durante a fase, plugue de verdade
(o adaptador já foi desenhado para isso); se não fornecer, o adaptador provisório é a entrega
completa e correta desta fase.

### 2.9 Catálogo de permissões já completo — confirmado, não redecidido

`apps/api/migrations/seed_dev.py::CATALOGO_PERMISSOES` (você **não edita este arquivo**) já semeia,
linha a linha:

```
("identidade", "delegacoes", CRUD,                    False, "Delegacoes temporarias")
("jornada",    "afastamentos", CRUD + (APROVAR,),      True,  "Afastamentos")            # F3, já semeado
("jornada",    "tipos_afastamento", (CRIAR,EDITAR,LER),False, "Tipos de afastamento")     # F3, já semeado
("workflow",   "solicitacoes", CRUD + (APROVAR,),      False, "Solicitacoes")
("workflow",   "aprovacoes",   (LER, APROVAR),         False, "Etapas de aprovacao")
("workflow",   "notificacoes", (LER, CRIAR),           False, "Notificacoes")
("workflow",   "tipos_solicitacao", (CRIAR, LER),      False, "Tipos de solicitacao")
("fechamento", "periodos",     CRUD,                   False, "Periodos de apuracao")
("fechamento", "fechamentos",  (LER,CRIAR,EDITAR,EXECUTAR) + (REABRIR,), False, "Fechamento de periodo")
("fechamento", "espelhos",     (LER, CRIAR, EXPORTAR, ASSINAR), False, "Espelho de ponto")
```

Os valores de `x-permissao` usados pelo `openapi.yaml` nesta fase são exatamente: `solicitacoes.ler`,
`solicitacoes.criar`, `solicitacoes.editar` (usada por `cancelarSolicitacao`), `tipos_solicitacao.ler`,
`tipos_solicitacao.criar`, `aprovacoes.ler`, `aprovacoes.aprovar`, `delegacoes.ler`, `delegacoes.criar`,
`periodos.ler` (confirme o exato lendo a rota — pode ser `periodos.ler`/`criar`, leia
`routers/fechamentos.py` gerado), `fechamentos.criar`, `fechamentos.ler`, `fechamentos.executar` (usada
por `conferirFechamento`), `fechamentos.reabrir`, `espelhos.ler`, `espelhos.criar`, `espelhos.assinar`.
Note que `afastamentos.aprovar` **está semeada mas não é usada por nenhuma rota da tag `afastamentos`**
(F3 não expõe uma "decidir afastamento" própria) — isto confirma o desenho do §2.3: a aprovação de
`ferias`/`afastamento` passa pela cadeia genérica de `aprovacoes` (`aprovacoes.aprovar`), não por uma
permissão dedicada em `afastamentos`. **Você não precisa completar catálogo nenhum.**

### 2.10 Filas e cron — o que já existe, o que esta fase acrescenta (com justificativa)

`apps/worker/worker/tarefas/__init__.py` (catálogo `TAREFAS`) tem hoje **nove** tarefas registradas
(`apurar_dia`, `recalcular_periodo`, `gerar_afd`, `gerar_aej`, `executar_relatorio`, `enviar_webhook`,
`sincronizar_terminal`, `expurgo_lgpd`, `importar_colaboradores`) — **nenhuma para fechamento, espelho
ou notificação**. `apps/worker/worker/scheduler.py::montar_cron()` tem hoje **duas** rotinas
(`verificar_banco_horas_vencendo`, `verificar_terminal_offline`), cada uma produzindo o único evento de
`events.yaml` com `origem: scheduler` que a justifica.

Esta fase **acrescenta três tarefas novas** ao catálogo do worker (mesmo precedente que a F2 já usou
para `importar_colaboradores` — leia o comentário no topo do próprio arquivo, que já numera "**Nove**
tarefas" e explica exatamente esse precedente) e **uma rotina de cron nova**, todos com justificativa
explícita, não por analogia solta:

| Tarefa nova | Fila | Corpo em | Agente | Por quê é assíncrona |
|---|---|---|---|---|
| `processar_fechamento` | `FILA_FECHAMENTO` (nova, `"ponto:fechamento"`) | `apps/worker/worker/tarefas/fechamento.py` (novo) | A2 | `criarFechamento` já é `202`/`ProcessamentoAssincrono` no contrato; fechar uma empresa inteira (centenas de vínculos × dias do período) não cabe no tempo de uma requisição HTTP |
| `gerar_espelhos` | `FILA_FECHAMENTO` | mesmo arquivo | A2 | `gerarEspelhos` também é `202`/`ProcessamentoAssincrono` no contrato (`tipo: espelho`, este valor já existe no enum) |
| `processar_fila_notificacoes` | `FILA_NOTIFICACOES` (nova, `"ponto:notificacoes"`) | `apps/worker/worker/tarefas/notificacoes.py` (novo) | A3 | drena `notificacoes.status='pendente'` e chama o adaptador de canal — não pode rodar dentro da requisição HTTP que criou a notificação |

| Rotina de cron nova | Frequência | Corpo em | Agente | Produz |
|---|---|---|---|---|
| `verificar_notificacoes_pendentes` | a cada 10 min | `apps/worker/worker/notificacoes_verificacao.py` (novo) | A3 | notificações de `jornada_excedida`/`sem_marcacao`/`banco_vencendo` (via `ocorrencias`) e "pendência há N dias" (via `solicitacoes`/`aprovacoes` com `prazo_em` vencido) — nenhum evento de `events.yaml` corresponde 1:1 a esta rotina (ela não publica um evento de domínio, só grava `notificacoes` e aciona o escalonamento de A1, §2.11); isto é uma decisão fixada por este PCF, não uma extensão do padrão restrito de `montar_cron()` original — documente essa diferença no docstring do módulo |

**A2 e A3 editam `apps/worker/worker/tarefas/__init__.py` e `apps/worker/worker/filas.py` na mesma
seção compartilhada** — regra de convivência: cada um acrescenta só a sua própria entrada, em ordem
alfabética dentro do bloco, sem tocar na entrada do outro nem renumerar o comentário de cabeçalho de
forma que colida (combine a ordem exata entre os dois antes de commitar; "**Nove** tarefas" vira
"**Doze** tarefas" — um único ajuste de texto, não dois).

**Nenhuma tarefa nova precisa de uma segunda função `SECURITY DEFINER` cara.** `verificar_
notificacoes_pendentes` só precisa saber **quais tenants existem** (não uma tabela de domínio inteira)
para então abrir uma sessão `ponto_app` normal por tenant com `SET LOCAL app.tenant_id` e fazer
consultas comuns, sob RLS, em `ocorrencias`/`solicitacoes`/`aprovacoes` — exatamente o padrão que
`verificar_banco_horas_vencendo` já usa **depois** de ter a lista de contas, só que aqui o "depois" é
por tenant, não por conta. Ver §5 para a única exceção de contrato: uma função nova e mínima,
`fn_tenants_ativos()`, que devolve **só** `(id, slug)` de tenants não suspensos — nada de domínio
específico, e por isso mais alinhada ao espírito de "exponha só o que a rotina precisa"
(`RFC-013`) do que replicar mais uma função de enumeração bespoke por domínio.

## 3. Leituras obrigatórias (lista fechada)

Leia isto e pare. Não leia código de F1/F2/F3/F5/F6/F8/F9a além dos módulos explicitamente listados.

- `packages/contracts/openapi.yaml` — **apenas** as tags `solicitacoes` (6 operações: `/v1/
  solicitacoes`, `/v1/solicitacoes/{solicitacaoId}`, `/v1/solicitacoes/{solicitacaoId}/cancelar`,
  `/v1/tipos-solicitacao`), `aprovacoes` (4 operações: `/v1/aprovacoes`, `/v1/aprovacoes/
  {aprovacaoId}/decidir`, `/v1/delegacoes`), `fechamentos` (7 operações: `/v1/periodos`, `/v1/
  fechamentos`, `/v1/fechamentos/{fechamentoId}`, `/v1/fechamentos/{fechamentoId}/conferir`, `/v1/
  fechamentos/{fechamentoId}/reabrir`), `espelhos` (5 operações: `/v1/espelhos`, `/v1/espelhos/
  {espelhoId}`, `/v1/espelhos/{espelhoId}/assinar`, `/v1/espelhos/{espelhoId}/pdf`). Note quais
  operações **não** existem, listadas no §2.7 (não invente `atualizarFechamento`, `excluirFechamento`,
  `atualizarEspelho`, `excluirSolicitacao` — é `cancelarSolicitacao`, não há PATCH em `aprovacoes` nem
  em `delegacoes`). Leia também `afastamentos`/`tipos-afastamento` (8 operações, já implementadas por
  F3 — **não edite os routers**, leia como consumidor do que já responde `200`/`201`) e, dentro da tag
  `apuracoes`/`tratamentos`/`banco-horas`, apenas os *schemas* `DecisaoRequisicao`, `Tratamento`,
  citados no §2. Leia também, em `components`: `parameters`, `responses`, `Problema`, e os schemas
  `Solicitacao*`, `TipoSolicitacao*`, `Aprovacao`, `Delegacao*`, `Periodo*`, `Fechamento*`,
  `ConferenciaResposta`, `ReaberturaRequisicao`, `Espelho*`, `AssinaturaEspelho*`,
  `ProcessamentoAssincrono`, `CancelamentoRequisicao`, `Afastamento*`, `TipoAfastamento*`.
- `packages/contracts/schema.sql` — seção **11 (WORKFLOW, APROVAÇÕES E NOTIFICAÇÕES)** por inteiro
  (`tipos_solicitacao`, `solicitacoes`, `aprovacoes`, `anexos`, `notificacoes`, `notificacao_
  preferencias`); seção **12 (FECHAMENTO E ESPELHO)** por inteiro (`periodos`, `fechamentos`,
  `espelhos`, `assinaturas_espelho`, e os `ALTER TABLE` que ligam `apuracoes_dia.fechamento_id`,
  `tratamentos.solicitacao_id`, `afastamentos.solicitacao_id`); seção **7**, apenas `tipos_afastamento`
  e `afastamentos` (já lidas por você para confirmar o que F3 entregou); seção **9**, apenas
  `tratamentos` (colunas `tipo_afastamento_id`, `solicitacao_id`, `status`, ver §2.2‑2.3); seção **15**
  (`auditoria`, linhas 3551‑3577, o `CHECK` de `acao` — já inclui `fechar`/`reabrir`/`assinar`/
  `aprovar`/`reprovar`). Leia também, **só para ler, nunca escrever**: `apuracoes_dia` (só a coluna
  `fechamento_id`), `identidade` (`delegacoes` — seção 4, `usuarios`).
- `packages/contracts/models/workflow.py` — `TipoSolicitacao`, `Solicitacao`, `Aprovacao`, `Anexo`,
  `Notificacao`, `NotificacaoPreferencia`. `packages/contracts/models/fechamento.py` — `Periodo`,
  `Fechamento`, `Espelho`, `AssinaturaEspelho`. `packages/contracts/models/identidade.py`, apenas
  `Delegacao`. `packages/contracts/models/jornada.py`, apenas `TipoAfastamento`, `Afastamento`. Mais
  `models/base.py`, `models/mixins.py`, `models/tipos.py`. **Confira o nome exato do arquivo lendo o
  diretório**, não adivinhe.
- `packages/contracts/errors.yaml` — categorias **PER** (todos os 4 códigos: 001 já usado por F4,
  002/003/004 são desta fase), **CONF** (001, 002, 003, 004), **VAL** (001, 005, 006, 007, 010, 011),
  **REC** (001, 002), e os transversais **AUTH**, **PERM**, **TEN**, **IDEM**, **RATE**, **INT**. Você
  **não cria código de erro novo** — os quatro `PER` e os quatro `CONF` já cobrem tudo que esta fase
  precisa (período fechado, já fechado, reabertura sem justificativa, fechamento com pendência
  bloqueante; registro duplicado, versão desatualizada, transição de estado inválida, registro com
  dependentes).
- `packages/contracts/events.yaml` — envelope de entrega e os eventos `ajuste.solicitado`, `ajuste.
  aprovado`, `ajuste.reprovado`, `periodo.fechado`, `periodo.reaberto`, `espelho.assinado`. Leia
  também `ocorrencia.aberta` e `banco_horas.vencendo` **só para entender o payload que o polling de
  A3 vai encontrar em `ocorrencias`**, não para publicá‑los de novo (você nunca publica eventos de
  outro domínio). Confirme que **nenhum outro evento** tem origem nesta fase (não existe
  `notificacao.enviada`, não invente).
- `packages/contracts/glossario.md` — seções 1, 1.1 (RLS), 1.2 (Imutabilidade); verbetes
  **Aprovação**, **Delegação** (se existir), **Escalonamento** (se existir), **Espelho**, **Fechamento**,
  **Notificação** (se existir), **Ocorrência**, **PTRP**, **Quitação**, **Solicitação**, **Tratamento**;
  seção 5 (sequência canônica) — releia com a extensão do §2 deste PCF em mente; seção 6 (termos
  proibidos).
- `docs/adr/ADR-002-imutabilidade-marcacao-camada-tratamento.md` — contexto de por que tratamento é a
  única correção legítima (não fala de assinatura; a decisão de assinatura está fixada no §2.4 deste
  PCF, a partir do próprio `schema.sql`).
- `docs/rfc/README.md` e `docs/backlog.md` — protocolo de RFC e onde anotar achados. Releia
  **RFC‑010** (precedente exato para o achado do `ProcessamentoAssincrono.tipo`, §2.7 item 3) e
  **RFC‑013** (precedente exato para a função `SECURITY DEFINER` mínima do §2.10/§5).
- `apps/api/app/core/seguranca.py`, `apps/api/app/db/sessao.py`, `apps/api/app/core/erros.py`,
  `apps/api/app/core/config.py` (para o padrão de leitura de variável de ambiente, precisa para a
  integração com MinIO) — andaime pronto de F1, você só usa.
- `apps/api/app/identidade/auditoria/hash_chain.py` — leia o módulo inteiro (é curto e a fórmula do
  hash está toda documentada na própria docstring). Reaproveite `gravar_auditoria` para fechamento,
  reabertura, assinatura e decisão de aprovação; **não reescreva a fórmula de hash em lugar nenhum
  desta fase** (a assinatura do espelho usa a MESMA função de canonicalização de JSON, não o
  chaining — ver §2.4).
- `apps/api/app/apuracao/tratamento/servico.py`, `decisao.py`, `eventos.py` — leia os três por
  inteiro, **só leitura, não edite** (ownership congelado de F4). É o módulo que você importa e chama
  em `decidir_tratamento` (§2.1). Leia também `apps/api/app/apuracao/tratamento/fechamento.py` (a
  cópia de F4 de `verificar_periodo_aberto`) só para saber que ela já existe e já trava tudo que
  precisa travar — você não a chama diretamente (não é exportada como "produzida" por F4), a trava já
  acontece dentro das rotas de F4 automaticamente quando você cria um `Fechamento`.
- `apps/api/app/apuracao/banco_horas/quitacoes.py` (ou o nome real do módulo — confirme lendo o
  diretório) — só leitura, para a materialização de `folga` (§2.3). Leia a assinatura real antes de
  chamar.
- `apps/api/app/routers/solicitacoes.py`, `aprovacoes.py`, `fechamentos.py`, `espelhos.py` — os
  *stubs* gerados pela Fase 0 (hoje respondem `501` com `PONTO-INT-005`). Leia como exemplo de
  assinatura de handler — não regere estes arquivos à mão. Note que `fechamentos.py` também contém as
  operações da tag `periodos` (`listarPeriodos`, `criarPeriodo`) e `aprovacoes.py` também contém as de
  `delegacoes` (`listarDelegacoes`, `criarDelegacao`) — mesmo arquivo, tags diferentes, é assim que a
  Fase 0 organizou.
- `apps/api/app/routers/tratamentos.py`, `apps/api/app/routers/apuracoes.py` — exemplo **vivo** de
  rotas já implementadas por F4 sobre este mesmo andaime, para copiar o padrão de handler.
- `apps/api/app/schemas/contrato.py` (gerado) — apenas para confirmar que os modelos Pydantic já
  existem (`Solicitacao`, `TipoSolicitacao`, `Aprovacao`, `Delegacao`, `Periodo`, `Fechamento`,
  `Espelho`, `AssinaturaEspelho`, `ProcessamentoAssincrono`, `ConferenciaResposta`,
  `ReaberturaRequisicao`, `DecisaoRequisicao`, `CancelamentoRequisicao`, e as variantes `*Criar`/
  `Lista*`) — **não edite**, é gerado.
- `apps/api/migrations/seed_dev.py` — leia **apenas** `CATALOGO_PERMISSOES` (§2.9), `TIPOS_TRATAMENTO`
  e `TIPOS_SOLICITACAO` (§2.2) por inteiro. **Você não edita este arquivo.**
- `apps/worker/worker/tarefas/__init__.py`, `apps/worker/worker/filas.py`, `apps/worker/worker/
  scheduler.py`, `apps/worker/worker/banco_horas_vencimento.py` (referência de forma para o módulo de
  suporte cross‑tenant que A3 vai criar), `apps/worker/worker/terminais_saude.py` (idem) — leia os
  cinco por inteiro. Você edita os três primeiros (adicionando, nunca removendo linha alheia — ver
  §2.10) e cria módulos novos inspirados nos dois últimos.
- `infra/.env.example` — confirme por si mesmo que não há SMTP/FCM/APNs/WhatsApp configurados (§2.8) e
  leia o bloco `# 6. MINIO` para as variáveis que você vai consumir em `app/core/config.py`.
- `docs/rfc/RFC-010-resolucao-de-terminal-e-tipo-sincronizacao.md` e `docs/rfc/RFC-013-enumeracao-
  cross-tenant-para-rotinas-de-manutencao.md` — leia as duas por inteiro, são o precedente direto dos
  dois achados do §2.7/§2.10.

## 4. Contratos

**Consome** — já existe, esta fase apenas usa:

- Tabelas `tipos_solicitacao`, `solicitacoes`, `aprovacoes`, `delegacoes`, `periodos`, `fechamentos`,
  `espelhos`, `assinaturas_espelho`, `notificacoes`, `notificacao_preferencias`, `anexos` — todas já
  existem desde a Fase 0 (seções 4, 11 e 12 do `schema.sql`). Você faz o CRUD/workflow completo sobre
  elas.
- Tabelas `tipos_afastamento`, `afastamentos` (F3, já com CRUD completo e testado) — leitura para
  resolver `tipo_afastamento_id`; **escrita apenas em `afastamentos`** para o caso `ferias` (criação
  direta de linha nova, §2.3) — você não toca em `tipos_afastamento`.
- Tabela `tratamentos` (F4) — **escrita** apenas via `criar_tratamento`/`decidir_tratamento` já
  implementados por F4 (você chama as funções, nunca faz `INSERT`/`UPDATE` direto na tabela).
- Módulo `app.apuracao.tratamento.decisao.decidir_tratamento` (F4) — assinatura real conforme o código,
  reaproveitada integralmente (§2.1). Módulo `app.apuracao.tratamento.servico.criar_tratamento` (F4) —
  idem, para criar o `Tratamento` em `pendente` antes de chamar `decidir_tratamento`.
- Módulo `app.apuracao.banco_horas.quitacoes` (F4) — leitura, para materializar `folga` (§2.3).
- Módulo `app.identidade.auditoria.hash_chain.gravar_auditoria` (F1) — função real, para fechamento,
  reabertura, decisão de aprovação e assinatura de espelho.
- Andaime da API (`app/core/erros.py`, `app/core/catalogo_erros.py`, `app/core/contexto.py`, `app/
  core/seguranca.py`, `app/db/sessao.py`, `app/core/config.py`), modelos Pydantic gerados em `app/
  schemas/contrato.py`, modelos SQLAlchemy do pacote `ponto_contracts`.
- Catálogo de permissões já semeado (§2.9) — `solicitacoes.*`, `tipos_solicitacao.*`, `aprovacoes.*`,
  `delegacoes.*`, `periodos.*`, `fechamentos.*`, `espelhos.*`, `afastamentos.*` (leitura),
  `notificacoes.{ler,criar}`.
- `apps/api/app/routers/__init__.py` — **já registra** os quatro roteadores desta fase na ordem
  correta. Você não toca neste arquivo.
- `apps/worker/worker/tarefas/__init__.py`, `apps/worker/worker/filas.py`, `apps/worker/worker/
  scheduler.py::montar_cron()` — você **acrescenta** entradas (§2.10), nunca remove ou reordena as
  existentes.

**Produz** — esta fase implementa:

*Endpoints (22 operações; hoje `501`):*

| Tag | Operações | Agente |
|---|---|---|
| `solicitacoes` (4) | `listarSolicitacoes`, `criarSolicitacao`, `obterSolicitacao`, `cancelarSolicitacao` | A1 |
| `solicitacoes`/tipos (2) | `listarTiposSolicitacao`, `criarTipoSolicitacao` | A1 |
| `aprovacoes` (2) | `listarAprovacoesPendentes`, `decidirAprovacao` | A1 |
| `aprovacoes`/delegações (2) | `listarDelegacoes`, `criarDelegacao` | A1 |
| `fechamentos`/períodos (2) | `listarPeriodos`, `criarPeriodo` | A2 |
| `fechamentos` (5) | `criarFechamento`, `listarFechamentos`, `obterFechamento`, `conferirFechamento`, `reabrirFechamento` | A2 |
| `espelhos` (5) | `listarEspelhos`, `gerarEspelhos`, `obterEspelho`, `assinarEspelho`, `baixarEspelhoPdf` | A2 |

A permissão exigida por operação é o valor de `x-permissao` no `openapi.yaml` (§2.9). Use exatamente
esse valor.

*Tabelas escritas:* `tipos_solicitacao`, `solicitacoes`, `aprovacoes`, `delegacoes`, `periodos`,
`fechamentos`, `espelhos`, `assinaturas_espelho`, `notificacoes`, `notificacao_preferencias` — as 10
tabelas do grupo 11 e 12 do glossário. Escrita **restrita e documentada** (§2.3) em `afastamentos`
(só o caso `ferias`, criação de linha nova) e em `tratamentos` (só via as funções de F4, nunca
`INSERT`/`UPDATE` direto). Leitura apenas em `tipos_afastamento`, `apuracoes_dia` (só `fechamento_id`),
`auditoria` (só via `gravar_auditoria`).

*Módulos internos publicados para outras fases (assinatura fixada por este PCF):*

- `app.workflow.solicitacoes.materializacao.materializar_solicitacao_aprovada(sessao, tenant_id,
  solicitacao, *, aprovador_usuario_id) -> None` — despachante genérico de A1 (§2.3). F11/F12 não
  precisam dele diretamente, mas se uma fase futura precisar disparar a mesma lógica de fora, é este
  o ponto de entrada.
- `app.workflow.solicitacoes.afastamentos.materializar_ferias_ou_folga(sessao, tenant_id,
  solicitacao, *, aprovador_usuario_id) -> None` — ramo de A4, chamado pelo despachante acima.
- `app.notificacao.motor.processar_evento(sessao, tenant_id, envelope: dict[str, Any]) -> int` (devolve
  a quantidade de linhas de `notificacoes` criadas) — módulo de A3, chamado em processo por A1/A2/A4
  logo após cada `publicar(envelope)` local (§2.7).
- **Assinaturas fixadas por este PCF** — se mudarem, atualize todos os usos no mesmo commit.

*Eventos publicados:* `ajuste.solicitado` (em `criarSolicitacao`, **apenas** quando `categoria ==
'ajuste_ponto'`, §2.7), `ajuste.aprovado`/`ajuste.reprovado` (via `decidir_tratamento` de F4 quando a
categoria materializa tratamento; publicados diretamente por A4 quando a categoria é `ferias`/`folga`
— módulo próprio `app/workflow/solicitacoes/eventos.py`, mesmo padrão replicado por F2‑F5/F4, nunca
importado de outra fase), `periodo.fechado` (ao concluir `criarFechamento`), `periodo.reaberto` (em
`reabrirFechamento`), `espelho.assinado` (em `assinarEspelho`, só quando `aceite=true`). Envelope
exato de `events.yaml`; crie seu próprio módulo `app/workflow/eventos.py` (A1) e `app/workflow/
fechamento/eventos.py` (A2) com `montar_envelope`/`publicar`.

**Não toca** — é de outra fase, mesmo que pareça relacionado:

- **Cálculo, apuração, banco de horas** — F4, já concluída. Você consome `decidir_tratamento`/
  `criar_tratamento`/o módulo de quitações; nunca duplica a lógica de recálculo, hora extra, FIFO/
  LIFO ou hash chain do extrato.
- **Marcação** — F5, já concluída. Você nunca lê nem escreve `marcacoes`.
- **Jornada, escala, feriado, resolvedor** — F3, já concluída. `afastamentos`/`tipos_afastamento` são
  F3; você só lê (exceto a criação de linha em `afastamentos` para `ferias`, §2.3).
- **Painel RH/gestor** (`apps/web`) — F9b, já concluída. **Nenhum arquivo de `apps/web` é tocado nesta
  fase.** F9b já tem suporte parcial de UI para apuração (`dialogo-de-recalculo.tsx`) mas nenhuma tela
  de aprovação/fechamento ainda — isso é trabalho de UI futuro (F11 se precisar, ou uma fase de
  polimento; **não é desta fase, que é backend puro**). **F8 (portal do colaborador, já concluída) já
  tem páginas e hooks React apontando para as operações desta fase** (`apps/web/src/app/eu/
  solicitacoes/`, `apps/web/src/ganchos/use-solicitacoes.ts`, `use-tipos-solicitacao.ts`, `use-
  espelho-de-ponto.ts`) — hoje batendo em `501`. Você não edita nada em `apps/web`, mas **os `campos`/
  formato de resposta das suas rotas precisam bater exatamente com o schema gerado do contrato**
  (que já é o mesmo que F8 consome) para que essas telas passem a funcionar sem qualquer mudança
  nelas.
- **Relatórios, espelho com layout de designer, agendamento por e‑mail** — F11. Você entrega o PDF
  funcional e legal do espelho (§2.5); a F11 refina visual sobre os mesmos dados.
- **AFD, AEJ, assinatura CAdES, `rep_ps`** — F12. Um tratamento nunca gera linha de AFD
  (`tipos_tratamento.afeta_afd = FALSE`, já garantido por `CHECK`, herdado de F4).
- **Entrega de webhook** (assinatura HMAC, retentativa, DLQ) — F13. Você só publica no barramento
  interno de cada domínio próprio (§2.7); não implementa entrega HTTP a terceiros.
- **WhatsApp via OpaSuite** — decisão do dono do produto, fora do escopo (§2.8). Não implemente
  nenhuma chamada HTTP à API do OpaSuite.
- **eSocial (S‑2230 e demais eventos)** — integração externa listada em `PROJETO.md` §10, tratada
  como leitura futura por outra fase; esta fase não emite nenhum evento eSocial.
- `packages/contracts/**` — **congelado**, com a **única exceção explícita** desta fase (§5): a função
  `fn_tenants_ativos()`, decisão nova fixada por este PCF (não uma RFC pré‑aprovada como a de F4/
  RFC‑013, mas seguindo o mesmo padrão de forma).
- `apps/mobile`, `apps/device-gw`, `apps/facial-svc`.

## 5. Ownership de arquivos

Caminhos **exclusivos** desta fase.

| Agente | Caminhos |
|---|---|
| **A1** (motor de solicitações) | `apps/api/app/workflow/solicitacoes/**` (exceto `afastamentos.py`, ownership de A4 — ver linha compartilhada abaixo)<br>`apps/api/app/workflow/aprovacoes/**`<br>`apps/api/app/routers/solicitacoes.py`<br>`apps/api/app/routers/aprovacoes.py`<br>`apps/api/tests/f10/solicitacoes/**`<br>`apps/api/tests/f10/aprovacoes/**` |
| **A2** (fechamento) | `apps/api/app/workflow/fechamento/**` (inclui espelho e assinatura)<br>`apps/api/app/comum/armazenamento.py` (novo, cliente MinIO — reaproveitável por A4)<br>`apps/api/app/routers/fechamentos.py`<br>`apps/api/app/routers/espelhos.py`<br>`apps/worker/worker/tarefas/fechamento.py` (novo)<br>`apps/api/tests/f10/fechamento/**`<br>`apps/api/tests/f10/espelhos/**` |
| **A3** (notificações) | `apps/api/app/notificacao/**` (novo: `motor.py`, `preferencias.py`, `mensagens.py`, `canais/push.py`, `canais/email.py`, `canais/in_app.py`)<br>`apps/worker/worker/tarefas/notificacoes.py` (novo)<br>`apps/worker/worker/notificacoes_verificacao.py` (novo)<br>`apps/api/tests/f10/notificacao/**` |
| **A4** (férias, afastamentos e abonos) | `apps/api/app/workflow/solicitacoes/afastamentos.py` (novo — único arquivo de A4 dentro do pacote de A1, ver linha compartilhada abaixo)<br>`apps/api/tests/f10/afastamentos_workflow/**` (inclui os testes de `abono` que exercitam o despachante genérico de A1, sem editar o código de A1) |

**Compartilhado dentro da fase** (exige combinação entre os agentes da fase):

| Caminho | Regra |
|---|---|
| `apps/api/app/workflow/__init__.py` | Criado por **A1** na T1 (primeira tarefa de código da fase), docstring e nada mais. Ninguém acrescenta código aqui. |
| `apps/api/app/workflow/solicitacoes/afastamentos.py` | Ownership exclusivo de **A4** (ver tabela acima), mas o **arquivo que o importa** (`app/workflow/solicitacoes/materializacao.py`, de A1) faz `from app.workflow.solicitacoes.afastamentos import materializar_ferias_ou_folga` — combine a assinatura exata (§2.3) antes de qualquer um dos dois escrever a chamada. |
| `apps/worker/worker/tarefas/__init__.py` | Compartilhado **por bloco de import + tupla `TAREFAS`**: **A2** acrescenta `processar_fechamento`, `gerar_espelhos` (de `worker.tarefas.fechamento`); **A3** acrescenta `processar_fila_notificacoes` (de `worker.tarefas.notificacoes`). Import em ordem alfabética, sem remover/reordenar linha alheia; atualize "Nove tarefas" → "Doze tarefas" no docstring em **um único commit combinado** entre A2 e A3 (não dois commits divergentes). |
| `apps/worker/worker/filas.py` | Mesma regra: **A2** acrescenta `FILA_FECHAMENTO` e as duas entradas de `FILA_POR_TAREFA`/`FASE_POR_TAREFA`; **A3** acrescenta `FILA_NOTIFICACOES` e a entrada correspondente. |
| `apps/worker/worker/scheduler.py` | Só **A3** edita — acrescenta `verificar_notificacoes_pendentes` a `ROTINAS`, `montar_cron()` e a lista `__all__`, sem tocar nas duas rotinas existentes de F4/F6. |
| `apps/api/tests/f10/conftest.py` | Só **A1** edita (T1). Fixture com tenant + empresa + unidade + colaborador com vínculo `apura_ponto=true` + jornada simples atribuída (INSERT direto, tabelas de F3) + um `TipoTratamento`/`TipoSolicitacao`/`TipoAfastamento` de exemplo (reaproveitando os já semeados por `seed_dev.py` quando possível, ou INSERT direto equivalente) + um `Periodo` aberto cobrindo o mês corrente. A2, A3 e A4 **usam** a fixture; não editam — se precisarem de um dado a mais, pedem a A1. |

**Compartilhado com outras fases (contrato congelado) — exceção única e explícita:**

`packages/contracts/schema.sql` (seção 2, logo após as demais funções `SECURITY DEFINER` já
existentes) e `apps/api/migrations/versions/0001_inicial.py` recebem **uma única adição**: a função
mínima de enumeração cross‑tenant de tenants ativos, seguindo exatamente o padrão de forma de
`fn_resolve_tenant`/`fn_terminais_para_verificacao_saude`/`fn_bh_contas_para_verificacao_vencimento`
(as três já existem — leia como modelo):

```sql
-- Enumeracao cross-tenant minima para rotinas de cron que precisam apenas
-- saber "quais tenants existem" antes de abrir uma sessao por tenant (mesmo
-- padrao de RFC-013, aqui generalizado: em vez de expor colunas de UM
-- dominio especifico como as funcoes irmas ja fazem, esta expoe so a
-- identidade do tenant -- o cron entao publica SET LOCAL app.tenant_id por
-- tenant e faz consultas comuns, sob RLS, no dominio que precisar). Usada
-- por verificar_notificacoes_pendentes (F10/A3).
CREATE OR REPLACE FUNCTION fn_tenants_ativos()
RETURNS TABLE (
    id   UUID,
    slug TEXT
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.id, t.slug
    FROM tenants t
   WHERE t.status = 'ativo';
$$;

COMMENT ON FUNCTION fn_tenants_ativos() IS
  'Enumeracao cross-tenant minima (id, slug) de tenants ativos para rotinas de cron que operam por tenant (F10). Expoe so identidade, nunca dado de dominio.';
```

Confirme o nome exato da coluna de status em `tenants` (`status`, `ativo` booleano, ou outro) **lendo
a tabela real antes de escrever esta função** — o texto acima é a forma, não necessariamente o nome
exato da coluna. **A3 é quem escreve esta função**, em ambos os arquivos. Nenhuma outra linha de
`packages/contracts/**` muda; qualquer outra necessidade de alteração no contrato é RFC nova.

**Explicitamente fora do seu ownership** (não edite, nem "só para arrumar"):
`packages/contracts/**` (exceto a única função acima), `apps/api/app/schemas/contrato.py` (gerado),
`apps/api/app/core/catalogo_erros.py`, `apps/api/app/core/erros.py`, `apps/api/app/core/seguranca.py`,
`apps/api/app/core/middleware.py`, `apps/api/app/db/sessao.py`, `apps/api/app/main.py`,
`apps/api/app/routers/__init__.py`, `apps/api/app/routers/{auth,tenants,admin,auditoria,empresas,
unidades,organizacao,colaboradores,contratos,biometria,dispositivos,terminais,jornadas,escalas,
feriados,afastamentos,marcacoes,comprovantes,tratamentos,apuracoes,banco_horas,relatorios,fiscal,
webhooks,integracoes}.py`, `apps/api/app/apuracao/**` (F4, você só importa `tratamento.decisao`/
`tratamento.servico`/`banco_horas.quitacoes` como módulos read‑only), `apps/api/app/jornada/**`,
`apps/api/app/marcacao/**`, `apps/api/app/identidade/**` (exceto usar `hash_chain.gravar_auditoria`),
`apps/api/app/organizacao/**`, `apps/api/app/pessoas/**`, `apps/api/app/biometria/**`,
`apps/api/migrations/**` (inclusive `seed_dev.py`, exceto a migration citada acima),
`apps/api/tests/test_andaime.py`, `apps/worker/worker/tarefas/apuracao.py`, `apps/worker/worker/
banco_horas_vencimento.py`, `apps/worker/worker/terminais_saude.py`, `.github/workflows/**`,
`infra/**`, `Makefile`, `tasks.ps1`, `apps/web/**`, `apps/mobile/**`.

> **Nenhuma migration nova de tabela nesta fase.** As 10 tabelas dos grupos 11 e 12 já existem em
> `0001_inicial.py`. A única alteração de migration permitida é a função `SECURITY DEFINER` acima. Se
> você achar que precisa de outra coisa no schema, o contrato está errado: abra RFC.

## 6. Tarefas (T1..T16)

### T1 — Módulos de fronteira e fixture da fase
**Agente:** A1 (código) — todos os demais dependem desta tarefa
**Descrição:** Cria `apps/api/app/workflow/__init__.py` (docstring e nada mais) e `apps/api/tests/
f10/conftest.py` (fixture descrita em §5). Documenta no módulo que a fixture reaproveita, quando
possível, os tipos já semeados por `seed_dev.py` (T`IPOS_TRATAMENTO`/`TIPOS_SOLICITACAO`/tipos de
afastamento de fábrica) em vez de recriar dados equivalentes.
**Pronto quando:** `pytest apps/api/tests/f10 -q` coleta e a fixture sobe/derruba o banco sem erro.

### T2 — CRUD de tipos de solicitação e solicitações
**Agente:** A1
**Descrição:** `app/workflow/solicitacoes/tipos.py`: `listarTiposSolicitacao`, `criarTipoSolicitacao`
(valida `etapas` — cada entrada precisa de `papel` válido no enum de `aprovacoes.papel`; recusa com
`PONTO-VAL-001` se malformado). `app/workflow/solicitacoes/servico.py`: `criarSolicitacao` (gera
`protocolo` legível — formato `AAAA-NNNNNN` sequencial por tenant/ano, documente o algoritmo; cria a
primeira linha de `Aprovacao` conforme `tipos_solicitacao.etapas[0]`; recusa retroativo além de
`permite_retroativo_dias` com `PONTO-VAL-010`‑equivalente ou `PONTO-CONF-001` conforme o caso — decida
e documente qual, olhando `errors.yaml`; publica `ajuste.solicitado` **apenas** quando `categoria ==
'ajuste_ponto'`, §2.7), `listarSolicitacoes` (filtros do contrato: `colaboradorId`, `empresaId`,
`tipoSolicitacaoId`, `categoria`, `status`, `minhas`, `de`/`ate`), `obterSolicitacao`,
`cancelarSolicitacao` (`POST` que cancela — nunca DELETE físico; recusa cancelar solicitação já
`aprovada`/`reprovada`/`cancelada`/`expirada` com `PONTO-CONF-003`).
**Pronto quando:** teste prova protocolo único por tenant; teste prova que `ajuste_ponto` publica
`ajuste.solicitado` e as demais categorias não; teste prova `cancelarSolicitacao` idempotente‑negativo
(cancelar duas vezes falha na segunda).

### T3 — Fila de aprovação, decisão de etapa e despachante genérico de materialização
**Agente:** A1
**Descrição:** `app/workflow/aprovacoes/servico.py`: `listarAprovacoesPendentes` (fila do usuário
autenticado + etapas por delegação vigente — junte `Aprovacao.aprovador_usuario_id = sujeito.
usuario_id` **OU** uma `Delegacao` ativa cujo `delegado_usuario_id = sujeito.usuario_id` e
`delegante_usuario_id = aprovacao.aprovador_usuario_id`; filtro `atrasadas` compara `prazo_em` com
`now()` em tempo de consulta, sem gravar nada — decisão que evita precisar de um cron só para isto),
`decidirAprovacao` (aprovar avança `etapa_atual`/cria a próxima `Aprovacao` **ou**, se for a última
etapa, chama `app.workflow.solicitacoes.materializacao.materializar_solicitacao_aprovada` — T4 —,
marca `solicitacoes.status='aprovada'`, `concluida_em`, `resultado`; reprovar marca a etapa e a
solicitação como `reprovada`, publica `ajuste.reprovado` diretamente quando a categoria não passa
pelo caminho de tratamento de F4 — ou seja, para `ferias`/`folga`/categorias sem tratamento — e via
`decidir_tratamento` quando passa; grava `ip`/`user_agent`/`aprovador_delegacao_id` quando decidido
por delegação). `app/workflow/aprovacoes/delegacoes.py`: `listarDelegacoes`, `criarDelegacao` (valida
`inicioEm < fimEm`; recusa sobreposição de delegações ativas do mesmo `deleganteUsuarioId` com
`PONTO-VAL-010`).
**Pronto quando:** teste prova aprovação da última etapa materializa corretamente para cada categoria
da tabela do §2.2 (uma tabela de casos, não um teste por categoria copiado e colado); teste prova que
decisão por delegação fica marcada como tal na trilha de auditoria (`gravar_auditoria` com
`delegacao_id`); teste prova reprovação em qualquer etapa nunca materializa nada.

### T4 — Despachante genérico de materialização (Tratamento) e eventos próprios de aprovação
**Agente:** A1
**Descrição:** `app/workflow/solicitacoes/materializacao.py::materializar_solicitacao_aprovada`
(assinatura fixada §4): resolve `tipos_solicitacao.tipo_tratamento_id`; se preenchido, cria
`Tratamento(status='pendente', solicitacao_id=..., tipo_tratamento_id=..., ...)` a partir dos campos
de `Solicitacao` (`data_referencia`, `descricao`→`motivo`, `payload`→campos específicos por
categoria — documente o mapeamento por categoria no módulo, análogo ao `marcacoesPropostas` de
`ajuste_ponto`) e chama `app.apuracao.tratamento.decisao.decidir_tratamento` (aprovar); se a categoria
for `ferias`/`folga`, chama `app.workflow.solicitacoes.afastamentos.materializar_ferias_ou_folga`
(A4, T12); caso contrário (sem tratamento e fora de `ferias`/`folga`), não faz nada além de marcar
`aprovada` (§2.2). `app/workflow/solicitacoes/eventos.py`: `publicar_ajuste_reprovado` próprio (usado
só quando a reprovação não passa por `decidir_tratamento`, isto é, categorias `ferias`/`folga`),
mesmo padrão `BARRAMENTO_INTERNO` de F2‑F5.
**Pronto quando:** teste de mesa cobre as sete linhas da tabela do §2.2; teste prova que uma
categoria configurada pelo tenant com `tipo_tratamento_id` próprio (fora do seed de fábrica) também
materializa corretamente (prova que o despachante é genérico, não uma lista fixa de `if categoria ==`).

### T5 — Períodos e ciclo de vida do fechamento
**Agente:** A2
**Descrição:** `app/workflow/fechamento/periodos.py`: `listarPeriodos`, `criarPeriodo` (recusa
sobreposição de código único `uq_periodos_codigo`, recusa `dataFim < dataInicio` já garantido por
`CHECK` mas com mensagem melhor via `PONTO-CONF-001`). `app/workflow/fechamento/servico.py`:
`criarFechamento` — cria a linha `Fechamento(status='em_andamento')` **de forma síncrona** dentro da
própria requisição (decisão fixada: o `202`/`ProcessamentoAssincrono` do contrato é sobre o
**processamento pesado**, não sobre a criação do registro — mesma distinção que F4 fez entre criar um
`Tratamento` síncrono e enfileirar `recalcular_periodo`), roda a conferência (T6) **na mesma
transação**: se houver pendência bloqueante e `forcar` for falso, recusa com `PONTO-PER-004` e **não**
cria a linha; caso contrário, enfileira `processar_fechamento` (worker, T8) passando
`fechamento.id`, devolve `202` com `ProcessamentoAssincrono(id=fechamento.id, status="enfileirado")`
— **sem preencher `tipo`** (§2.7 item 3). `listarFechamentos`, `obterFechamento`. `reabrirFechamento`
(exige `motivo` — o `CHECK` do banco já impede sem ele, mas valide antes para devolver `PONTO-PER-003`
com mensagem clara em vez do erro cru do `CHECK`; atualiza `status='reaberto'`,
`reaberto_por`/`reaberto_em`/`motivo_reabertura`; grava `gravar_auditoria(entidade="fechamentos",
acao="reabrir", ...)`; publica `periodo.reaberto` com `espelhosInvalidados` contando quantos espelhos
`tipo='oficial'` daquele período ficam "desatualizados" — sem apagar nem alterar nenhum, apenas
contando).
**Pronto quando:** teste prova `criarFechamento` recusa com `PONTO-PER-004` quando há pendência
bloqueante e `forcar=false`, e aceita com `forcar=true` registrando o total; teste prova
`reabrirFechamento` sem `motivo` responde `PONTO-PER-003`; teste prova reabertura grava exatamente uma
linha em `auditoria` com `acao='reabrir'` e o motivo em `metadados`/`valor_novo`.

### T6 — Conferência prévia e as pendências bloqueantes
**Agente:** A2
**Descrição:** `app/workflow/fechamento/conferencia.py::conferir(sessao, tenant_id, fechamento_id
| escopo_pedido) -> ConferenciaResposta` — conta colaboradores/dias no escopo, ocorrências abertas
(`ocorrencias` sem resolução), solicitações pendentes (`solicitacoes.status IN ('pendente',
'em_aprovacao')` no escopo), dias ainda não apurados (`apuracoes_dia.tipo_dia = 'nao_apurado'` ou
ausência de linha para um dia útil esperado). Define **precisamente** quais códigos entram em
`bloqueantes` — decisão fixada: `marcacao_impar`, `sem_marcacao`, `nao_apurado` são bloqueantes por
padrão (jornada incompleta não deveria fechar sem revisão); `jornada_excedida`/`extra_excedida`/
`intrajornada_suprimida` não são bloqueantes por padrão (são fatos já corretamente apurados, apenas
avisos). Exponha `conferirFechamento` (`POST /v1/fechamentos/{fechamentoId}/conferir`) chamando esta
mesma função sobre um `Fechamento` já existente (não trava nada, só recomputa e devolve
`ConferenciaResposta`, atualizando `conferido_em`/`conferido_por` e `status='conferido'` quando ainda
`em_andamento`).
**Pronto quando:** teste prova que `podeFechar=false` quando existe `ocorrencias` com código
bloqueante aberta; teste prova que chamar `conferirFechamento` duas vezes seguidas sem mudança de
estado é idempotente (mesmos totais, sem duplicar contagem).

### T7 — Geração de espelho, PDF e integração com MinIO
**Agente:** A2
**Descrição:** `app/workflow/fechamento/espelho.py::gerar_espelho_do_vinculo(sessao, tenant_id,
periodo, vinculo_id, tipo, *, fechamento_id=None) -> Espelho` — monta `conteudo` (JSON com dias,
apuração, tratamentos identificados como lançamento manual, totais) lendo `apuracoes_dia`/
`apuracao_componentes`/`tratamentos` do vínculo no intervalo do período (**só leitura**), calcula
`hash_sha256` com a MESMA canonicalização de `hash_chain._json_canonico` (§2.4), grava com `versao`
incrementada respeitando `uq_espelhos_versao`. Se `gerarPdf`, gera o PDF (§2.5, biblioteca à sua
escolha, documentada) e grava via `app/comum/armazenamento.py` (novo, cliente MinIO — §2.5),
preenchendo `conteudo_ref` com a chave do objeto. Handler `gerarEspelhos`: resolve o escopo
(`vinculoIds` explícitos ou todo o escopo empresa/unidade), enfileira `gerar_espelhos` (worker, T8),
devolve `202`/`ProcessamentoAssincrono(tipo="espelho", ...)`. `listarEspelhos`, `obterEspelho`,
`baixarEspelhoPdf` (devolve o PDF do storage, ou gera sob demanda se `conteudo_ref` estiver vazio —
decida e documente qual das duas).
**Pronto quando:** teste prova que a soma dos totais do `conteudo` bate com os totais das colunas
(`totalTrabalhadoMinutos` etc.); teste prova que gerar um segundo espelho `oficial` para o mesmo
período/vínculo cria `versao=2` sem apagar `versao=1`; teste prova que o PDF gerado contém os campos
mínimos exigidos (nome do colaborador, período, totais — teste de conteúdo textual extraído do PDF,
não só "gerou bytes").

### T8 — Assinatura eletrônica e verificação
**Agente:** A2
**Descrição:** `app/workflow/fechamento/assinatura.py::assinarEspelho` — implementa a fórmula do
§2.4: recusa se `AssinaturaEspelhoRequisicao.hashSha256` não bater com `espelhos.hash_sha256`
(`PONTO-CONF-003` ou `PONTO-VAL-001`, decida e documente); grava `AssinaturaEspelho(metodo=
'aceite_eletronico', hash_assinado=..., carimbo_tempo=now(), ip=..., user_agent=..., status=
'assinado' se `aceite=true` senão `'recusado'` com `recusa_motivo`); publica `espelho.assinado`
**apenas** quando `aceite=true`; grava `gravar_auditoria(entidade="espelhos", acao="assinar", ...)`.
Implementa o teste de verificação/não repúdio do §2.4 item 6.
**Pronto quando:** teste prova recusa de assinatura com hash divergente (`espelho` mudou entre a
exibição e o clique); teste prova `UPDATE`/`DELETE` direto em `assinaturas_espelho` falha com
`ERRCODE 42501` (role de aplicação real, mesmo padrão de evidência de F4 para `bh_lancamentos`); teste
prova que recomputar `SHA256` do `conteudo` do espelho e comparar com `hash_assinado` confirma a
assinatura, e que uma alteração hipotética do `conteudo` (via SQL direto, simulando adulteração)
quebra essa conferência — é a prova de "verificável e não repudiável" do critério de aceite.

### T9 — Tasks assíncronas de fechamento e espelho no worker
**Agente:** A2
**Descrição:** `apps/worker/worker/tarefas/fechamento.py` (novo): `processar_fechamento(ctx,
fechamento_id, tenant_id, ...)` chama a trava real (marca `apuracoes_dia.fechamento_id` para todo o
escopo, `status='fechado'`, `fechado_em`/`fechado_por`, `hash_conteudo` = hash do conjunto de
apurações travadas — decida e documente a fórmula, reaproveitando o padrão de canonicalização), gera
espelhos se `gerarEspelhos=true` foi pedido (chamando `gerar_espelho_do_vinculo` diretamente, não via
fila aninhada), publica `periodo.fechado`. `gerar_espelhos(ctx, ...)` chama `gerar_espelho_do_vinculo`
por vínculo do escopo. Registra as duas em `apps/worker/worker/tarefas/__init__.py`/`filas.py` (§5,
linha compartilhada).
**Pronto quando:** teste (via fixture de worker, mesmo padrão de F4 se F4 tiver criado uma) prova que
`processar_fechamento` travando 50 vínculos × 30 dias sintéticos completa e publica exatamente um
`periodo.fechado`; teste prova que uma segunda chamada a `criarFechamento` para o mesmo período/escopo
já fechado responde `PONTO-PER-002` (via a checagem síncrona da T5, não do worker).

### T10 — Motor de notificações: regras, preferências e mensagens
**Agente:** A3
**Descrição:** `app/notificacao/motor.py::processar_evento(sessao, tenant_id, envelope) -> int`
(assinatura fixada §4) — mapeia `envelope["tipo"]` para um conjunto de regras (destinatário,
título/corpo por evento — `app/notificacao/mensagens.py`, um template por `evento` × canal, em
português, sem dado sensível no corpo além do que o próprio evento já expõe), resolve destinatários
(usuário do colaborador quando existir vínculo `usuarios`↔`colaboradores`; gestor da hierarquia
quando o evento for de aprovação pendente — reaproveite a hierarquia já resolvida por F1/F2, só
leitura), consulta `notificacao_preferencias` (linha específica evento+canal, ou coringa `*`, ou
ausência = padrão do tenant habilitado) e `janela_inicio`/`janela_fim` (fora da janela, grava com
`agendada_para` no início da próxima janela em vez de `enviada` imediatamente). Cria uma linha de
`Notificacao` **por canal aplicável** (mesmo evento pode gerar duas linhas, push + in‑app, cada uma
com seu próprio ciclo — já documentado no comentário da tabela). `app/notificacao/preferencias.py`:
funções de leitura/gravação de preferência (sem endpoint HTTP — não existe rota para isto, §2.7 item
1; é só a lógica interna, pronta para o dia em que o endpoint existir).
**Pronto quando:** teste prova que `processar_evento` para `ajuste.aprovado` cria a linha certa para
o colaborador; teste prova que uma preferência `habilitado=false` para aquele evento+canal impede a
criação da linha; teste prova que fora da janela de silêncio a notificação é criada com
`agendada_para` futuro, não `enviada`.

### T11 — Canais de envio e a rotina de varredura cross‑tenant
**Agente:** A3
**Descrição:** `app/notificacao/canais/push.py`, `.../email.py`, `.../in_app.py` — cada um com
`enviar(notificacao) -> bool` (interface fixada, documentada); `in_app.py` só marca `enviada_em`
(não há transporte real, a linha em si é o "canal"); `push.py`/`email.py` implementam o adaptador
provisório do §2.8 (log estruturado + `status='enviada'`), claramente documentado como aguardando
credencial real, com o ponto de plugue óbvio (`# TODO F10+N: trocar por chamada real ao FCM/SMTP
quando houver credencial`). `apps/worker/worker/tarefas/notificacoes.py` (novo):
`processar_fila_notificacoes(ctx)` drena `notificacoes.status='pendente' AND (agendada_para IS NULL
OR agendada_para <= now())`, chama o canal certo, atualiza `status`/`enviada_em`/`tentativas`/`erro`.
`apps/worker/worker/notificacoes_verificacao.py` (novo): `listar_tenants_ativos_cross_tenant(config)`
via `fn_tenants_ativos()` (§5); por tenant, `SET LOCAL app.tenant_id` e consulta `ocorrencias`
recentes com código em `{jornada_excedida, sem_marcacao, banco_vencendo}` sem `notificacoes`
correspondente ainda (`NOT EXISTS (... entidade='ocorrencias' AND entidade_id=ocorrencia.id)`) e
`aprovacoes`/`solicitacoes` com `prazo_em` vencido sem notificação de "pendência" ainda — para cada
achado, chama `processar_evento` com um envelope sintético equivalente ao evento original (mesmo
formato de `dados`, reconstituído a partir da linha da tabela, já que o evento original não está mais
disponível em memória, §2.7). `apps/worker/worker/scheduler.py`: acrescenta
`verificar_notificacoes_pendentes` a `ROTINAS`/`montar_cron()`/`__all__` (§5, linha compartilhada, só
A3 edita).
**Pronto quando:** teste prova que rodar a varredura duas vezes seguidas sem nova ocorrência não
duplica notificação (idempotência via `NOT EXISTS`); teste prova que a rotina enumera ocorrências de
**dois tenants diferentes** numa única chamada de `fn_tenants_ativos()` sem `app.tenant_id` publicado
(mesma prova de SECURITY DEFINER que F4/F6 já fizeram); teste prova que `processar_fila_notificacoes`
avança `status` de `pendente` para `enviada` chamando o adaptador certo por `canal`.

### T12 — Materialização de férias e folga
**Agente:** A4
**Descrição:** `app/workflow/solicitacoes/afastamentos.py::materializar_ferias_ou_folga` (assinatura
combinada com A1, §5): para `categoria='ferias'`, resolve `tipo_afastamento_id` (§2.3), cria
`Afastamento` respeitando `ex_afastamentos_sobreposicao`, trata a violação com mensagem de negócio
clara; para `categoria='folga'`, chama o serviço de banco de horas de F4 (§2.3, leia a assinatura real
antes) para consumir o saldo equivalente ao período pedido. Em ambos os casos publica `ajuste.
aprovado` (evento próprio de A1, §4) com `tratamentoId` ausente do payload — decisão já fixada e o
achado de contrato já registrado no §2.7 item 4 (`tratamentoId` é `required` em `events.yaml` mas não
existe para estas categorias); você só implementa a decisão, não a redecide.
**Pronto quando:** teste prova `ferias` aprovada cria `Afastamento` com `status='aprovado'` e que o
resolvedor de F3 (`resolver_jornada_do_dia`, chamado read‑only para prova, sem editar nada de F3) lê
esse afastamento como insumo normal a partir da data de início; teste prova sobreposição de férias
aprovadas do mesmo colaborador é recusada; teste prova `folga` aprovada debita o saldo de banco de
horas correto (comparando `bh_contas.saldo_atual_minutos` antes/depois).

### T13 — Abono, justificativa e afastamento retroativo — prova de reaproveitamento
**Agente:** A4
**Descrição:** Testes (não código novo — o código é o despachante genérico de A1, T4) em
`apps/api/tests/f10/afastamentos_workflow/test_abono_e_retroativo.py`: exercita, ponta a ponta, uma
solicitação `abono` e uma `afastamento` (retroativo) desde `criarSolicitacao` até a apuração do dia
mudar (chamando `apurar_dia`/`recalcular_periodo` de F4, read‑only sobre módulo de outra fase, só para
observar o efeito). Se algum campo do `payload`/mapeamento não estiver claro no despachante de A1,
reporte a A1 em vez de inventar — é o mesmo tipo de combinação de T3/T4.
**Pronto quando:** teste prova que aprovar um `abono_falta` faz a falta do dia sumir da apuração
(`apuracoes_dia.faltas_minutos` ou equivalente zera, confirme o nome exato da coluna lendo F4); teste
prova que aprovar um `afastamento` retroativo sobre um dia **já apurado** (fixture cria a apuração
antes) dispara o recálculo daquele dia especificamente, sem tocar nos vizinhos (mesma propriedade que
F4 T12 já provou para o motor — aqui você só prova que o gatilho desta fase produz o mesmo efeito).

### T14 — Anexos e o achado de contrato documentado
**Agente:** A4
**Descrição:** Nenhum código de upload — o achado do §2.7 item 2 já fixa a decisão. Escreva a entrada
em `docs/backlog.md` (se ainda não existir uma equivalente de F2/F3) descrevendo precisamente a
lacuna (`anexos`/`documentos` sem endpoint HTTP em nenhuma fase até aqui) e o impacto específico desta
fase (`tipos_solicitacao.exige_anexo=true`, ex.: `abono_falta`, não pode ser tecnicamente imposto via
API hoje — documente isso como uma limitação conhecida, não um bug seu). Se o tempo da fase permitir,
implemente **apenas** a função interna de storage (`salvar_anexo(sessao, *, entidade, entidade_id,
conteudo_bytes, nome_arquivo, ...) -> Anexo`, reaproveitando `app/comum/armazenamento.py` de A2) sem
expor rota nenhuma — pronta para o dia em que a RFC de upload for decidida.
**Pronto quando:** a entrada de backlog existe e descreve o achado com precisão (arquivo, tabela,
campo, impacto); se a função interna foi implementada, um teste prova que ela grava o objeto no MinIO
e a linha em `anexos` corretamente, sem rota HTTP associada.

### T15 — Testes de propriedade e e2e multicanal
**Agentes:** A1, A2, A3 (conjunto)
**Descrição:** `apps/api/tests/f10/e2e/test_fluxo_completo.py`: solicitação → aprovação (duas etapas,
gestor e RH, com um caso de delegação) → tratamento aplicado → apuração muda → notificações criadas
para push/e‑mail/in‑app em cada transição relevante (`ajuste.solicitado` notifica o(s) aprovador(es)
da primeira etapa; `ajuste.aprovado` notifica o colaborador) → fechamento do período → espelho gerado
→ assinatura do colaborador → reabertura com justificativa → novo espelho retificado. Prova, num único
teste de ponta a ponta, os quatro critérios de aceite oficiais.
**Pronto quando:** o teste completo passa; a saída real é colada no relatório da fase mostrando, para
cada transição, a linha de `notificacoes` criada e seu `status` final.

### T16 — Fechamento da fase
**Agentes:** A1, A2, A3 e A4
**Descrição:** Rodar todos os comandos da §8 e colar a saída real no relatório da fase, item a item
contra a §7.
**Pronto quando:** todos verdes, com saída colada, e `git status --short packages/contracts` mostra
**apenas** `M packages/contracts/schema.sql` (a função `fn_tenants_ativos`, §5), nenhum outro arquivo.

## 7. Critérios de aceite

O relatório final responde item a item, com saída real colada.

1. **Solicitação percorre a cadeia completa e reflete na apuração**: uma solicitação `ajuste_ponto`
   criada, aprovada em duas etapas (gestor, RH), materializa um `Tratamento` aprovado e o dia muda de
   resultado (`apuracoes_dia` diferente antes/depois, provado pelo e2e de T15).
2. **Fechar período trava edição**: depois de `criarFechamento` concluir, `criarTratamento`/
   `decidirTratamento`/`recalcularApuracoes`/`criarQuitacaoBancoHoras` (todos de F4, já implementados)
   respondem `PONTO-PER-001` para dias cobertos — prova de que a trava já implementada por F4 dispara
   corretamente a partir da linha que esta fase cria.
3. **Reabrir exige justificativa registrada com autor**: `reabrirFechamento` sem `motivo` responde
   `PONTO-PER-003`; com motivo, grava exatamente uma linha em `auditoria` com `acao='reabrir'`,
   `usuario_id` do autor e o motivo em `metadados`/`valor_novo`.
4. **Assinatura do colaborador é verificável e não repudiável**: `assinarEspelho` recusa hash
   divergente; a linha de `assinaturas_espelho` é imutável por gatilho real (`UPDATE`/`DELETE` falham
   com `ERRCODE 42501`, evidência colada); recomputar `SHA256` do `conteudo` do espelho confirma
   `hash_assinado`.
5. **Notificação chega nos canais reais (push/e‑mail/in‑app) em teste e2e** (WhatsApp explicitamente
   fora, §2.8): para cada transição relevante do e2e de T15, existe uma linha de `notificacoes` por
   canal aplicável, com `status` avançando até `enviada` (ou `agendada_para` futuro quando fora da
   janela de silêncio, com teste dedicado provando esse caminho também).
6. **Materialização correta por categoria**: as sete linhas da tabela do §2.2 têm teste próprio
   provando o efeito exato (tratamento criado e aprovado / afastamento criado / banco de horas
   debitado / nenhum efeito automático).
7. **Reaproveitamento de F4, não duplicação**: nenhuma linha desta fase escreve diretamente em
   `apuracoes_dia`, `apuracao_componentes`, `bh_lancamentos` ou faz `INSERT`/`UPDATE` direto em
   `tratamentos` fora das funções `criar_tratamento`/`decidir_tratamento` de F4 — prova por análise
   estática (grep) mais teste de integração.
8. **Trilha de auditoria correta**: fechamento, reabertura, assinatura e decisão de aprovação por
   delegação geram linha em `auditoria` com `acao`/`entidade`/`valor_anterior`/`valor_novo` corretos,
   verificados por `verificar_cadeia` (F1) sem divergência.
9. **`banco_horas`, `apuracoes`, `tratamentos` de F4 continuam verdes**: rodar a suíte de testes de F4
   (`pytest apps/api/tests/f4 -q`) depois das mudanças desta fase, sem regressão — prova de que nada
   nesta fase quebrou o que F4 já tinha.
10. **Toda rota declara `Depends(exigir_permissao(...))`** com exatamente o `x-permissao` do contrato
    — verificável por um teste que percorre o `openapi.yaml` e confere rota a rota (mesmo teste que F4
    já escreveu — reaproveite o padrão, não precisa reinventar).
11. **Eventos publicados batem campo a campo com `events.yaml`**: `ajuste.solicitado` (só
    `ajuste_ponto`), `ajuste.aprovado`/`reprovado`, `periodo.fechado`, `periodo.reaberto`, `espelho.
    assinado`.
12. **Cobertura ≥ 90%** em `app.workflow` e `app.notificacao` (`--cov=app.workflow --cov=app.
    notificacao --cov-report=term-missing`), saída real colada.
13. **Contrato quase intocado**: `git status --short packages/contracts` mostra somente a função
    `fn_tenants_ativos` em `schema.sql`; nenhum outro artefato de `packages/contracts` foi tocado.
14. **`apps/web` intocado**: `git status --short apps/web` não mostra nenhuma alteração.
15. Todos os comandos da §8 verdes, com saída real colada no relatório.

## 8. Comandos de verificação

Rode a partir da **raiz do repositório**, salvo onde indicado. Windows usa `.\tasks.ps1`;
Linux/macOS usa `make`.

Subir o banco:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d postgres redis minio
```

```powershell
.\tasks.ps1 up
```

Migrar:

```bash
cd apps/api && alembic upgrade head
```

```powershell
cd apps/api; alembic upgrade head
```

Lint, formatação e tipos (versões fixadas no CI: ruff 0.7.4, mypy 1.13.0; `mypy` roda de dentro de
cada diretório de app, sem argumento — RFC‑009/§6):

```bash
ruff check apps packages tests
ruff format --check apps packages tests
cd apps/api && mypy
cd apps/worker && mypy
```

```powershell
.\tasks.ps1 lint
.\tasks.ps1 typecheck
```

**Saída esperada:** `All checks passed!`, `NN files already formatted`,
`Success: no issues found in NNN source files`.

Testes da fase, com cobertura dos dois pacotes de domínio:

```bash
cd apps/api && pytest tests/f10 -q --cov=app.workflow --cov=app.notificacao --cov-report=term-missing
```

```powershell
cd apps/api; pytest tests/f10 -q --cov=app.workflow --cov=app.notificacao --cov-report=term-missing
```

**Saída esperada:** todos os testes passam; a linha `TOTAL` da cobertura ≥ 90%; nenhum `skip` nos
testes que exigem banco.

Regressão de F4 (não pode quebrar):

```bash
cd apps/api && pytest tests/f4 -q
```

Imutabilidade e não repúdio da assinatura, isoladas para evidência no relatório:

```bash
cd apps/api && pytest tests/f10/espelhos -q -k "imutavel or assinatura or hash" -s
```

Prova de `SECURITY DEFINER` cross‑tenant (o critério de aceite 11 estendido):

```bash
cd apps/api && pytest tests/f10/notificacao -q -k "cross_tenant or fn_tenants_ativos" -s
```

E2e multicanal completo (o critério de aceite 5):

```bash
cd apps/api && pytest tests/f10/e2e -q -v
```

**Saída esperada:** o teste de ponta a ponta passa, e a saída `-v` mostra cada etapa (solicitação,
aprovação, materialização, fechamento, espelho, assinatura, reabertura).

Regressão do andaime da Fase 0 (não pode quebrar):

```bash
cd apps/api && pytest tests/test_andaime.py -q
```

Inventário de rotas idêntico ao contrato:

```bash
cd apps/api && python tools/conferir_rotas.py
```

**Saída esperada:** `Inventario identico ao contrato (metodo, caminho e operationId).`

Contrato quase intocado (a exceção da §5 é o único diff esperado):

```bash
git status --short packages/contracts
git diff packages/contracts/schema.sql
```

**Saída esperada:** apenas `M packages/contracts/schema.sql`; o diff mostra exclusivamente a criação
de `fn_tenants_ativos()` e seu `COMMENT ON FUNCTION`.

`apps/web` intocado:

```bash
git status --short apps/web
```

**Saída esperada:** sem saída nenhuma (nada modificado).

Migration continua reversível contra banco real:

```bash
cd apps/api && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## 9. Proibições

1. **Não edite `packages/contracts/`** além da única adição explicitamente autorizada por este PCF
   (`fn_tenants_ativos()`, §5). Qualquer outra divergência vira RFC nova em `docs/rfc/`.
2. **Não crie migration de tabela nova.** As 10 tabelas dos grupos 11 e 12 já existem em
   `0001_inicial.py`; a única alteração de migration permitida é a função da §5.
3. **Não crie código de erro novo.** Os quatro `PER` e os quatro `CONF` já cobrem tudo que esta fase
   precisa. Se faltar algo mesmo assim, é RFC.
4. **Não reescreva nem duplique lógica de F4.** `criar_tratamento`, `decidir_tratamento`, cálculo de
   apuração, consumo FIFO/LIFO de banco de horas — tudo isso é importado, nunca reimplementado. Se a
   assinatura de um módulo de F4 não bastar, é RFC — não invente um segundo caminho.
5. **Não escreva em `apuracoes_dia`, `apuracao_componentes` ou `bh_lancamentos`.** Você só lê. A
   escrita acontece exclusivamente via os módulos de F4 que você chama.
6. **Não invente `GET /v1/notificacoes` nem qualquer rota de `anexos`/`documentos`.** São achados de
   contrato documentados no §2.7, não uma lacuna para você preencher por conta própria.
7. **Não implemente nenhuma chamada HTTP real a um provedor de push/e‑mail/WhatsApp sem
   credencial configurada.** O adaptador provisório do §2.8 é a entrega completa e correta enquanto
   não houver credencial real — não simule uma integração que pareça real sem ser.
8. **Não toque em `apps/web` nem em `apps/mobile`.** Esta fase é backend puro. Se uma tela nova for
   necessária, é achado para F11 ou uma fase de UI — registre em `docs/backlog.md`.
9. **Não gere um PDF de espelho com "layout de designer".** O funcional e legal basta; a F11 refina o
   visual depois sobre os mesmos dados (§2.5). Investir tempo além disso é desperdício desta fase.
10. **Não implemente a assinatura CAdES/ICP‑Brasil do REP‑P.** Isso é a F12, sobre o AFD/AEJ — assunto
    completamente diferente da assinatura de aceite do espelho (§2.4).
11. **Não invente uma quarta forma de materialização.** Só existem os dois caminhos do §2.3 (tratamento
    via F4, ou `ferias`/`folga` via A4); qualquer categoria fora disso só marca `aprovada` sem efeito
    automático — se isso for insuficiente na prática, é achado de backlog, não invenção sua.
12. **Não invente endpoint que não existe no contrato** — em particular, não adicione
    `atualizarFechamento`, `excluirFechamento`, `atualizarEspelho`, `excluirEspelho`,
    `atualizarSolicitacao` (é `cancelarSolicitacao`), `atualizarAprovacao`, `atualizarDelegacao`,
    `excluirDelegacao`, `atualizarPeriodo`, `excluirPeriodo`. Se a ausência parecer defeito do
    contrato, é RFC.
13. **Não use os termos proibidos** da seção 6 do glossário: é *marcação* (nunca "batida"),
    *tratamento* (nunca "ajuste de marcação"), *apuração*, *colaborador*/*vínculo* (nunca
    "funcionário"), *tenant* (nunca "empresa" para dizer cliente do SaaS). Nesta fase, some: é
    *solicitação* (nunca "pedido" fora de texto de UI/mensagem ao usuário), *fechamento* (nunca
    "trava" como substantivo da entidade), *espelho* (nunca "folha de ponto" — termo de outro sistema).
14. **Não declare a fase pronta sem rodar os comandos da §8 e colar a saída real.** Em especial a
    prova de imutabilidade da assinatura (`ERRCODE 42501` real) e o teste e2e multicanal completo.
