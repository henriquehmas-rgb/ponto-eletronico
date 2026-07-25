# Glossário do Domínio — Ponto Eletrônico

> **Fonte da verdade do vocabulário.** Congelado na Fase 0 junto com `schema.sql`.
> Todo agente de fase lê este arquivo antes de escrever código. Se um termo usado
> no seu PCF não está aqui, isso é defeito do PCF — abra RFC, não invente sinônimo.
>
> Regra de ouro: **um conceito, um nome**. Não existe "batida" em alguns lugares e
> "marcação" em outros; não existe "ajuste" e "tratamento" para a mesma coisa.

---

## 1. Convenções do modelo de dados

Estas convenções valem para `schema.sql` e para todo código que o consome.

| # | Convenção | Detalhe |
|---|---|---|
| 1 | Idioma | Nomes de tabela, coluna, constraint e índice em **português do Brasil**, sem acento e sem cedilha, em `snake_case`. Código Python em `snake_case`, TypeScript em `camelCase`. |
| 2 | Chave primária | `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` em **todas** as 92 tabelas. `marcacoes` é a única com PK composta (`id, datahora_marcacao`), exigência do particionamento. |
| 3 | Enums | **TEXT + CHECK**, nunca tipo `ENUM` nativo. Escolha deliberada: adicionar valor com `ENUM` nativo exige `ALTER TYPE`, que não compõe bem com Alembic nem com tabela particionada, e o valor fica invisível no `\d`. Com `CHECK` o conjunto aceito é lido direto na definição da coluna. |
| 4 | Auditoria | `criado_em`, `criado_por`, `atualizado_em`, `atualizado_por` em toda tabela mutável. Tabelas *append-only* têm só `criado_em` e `criado_por` — porque não existe atualização para carimbar. |
| 5 | Soft delete | `excluido_em` e `excluido_por` **apenas em cadastros** (empresa, unidade, colaborador, jornada, perfil…). Nunca em marcação, lançamento, apuração, auditoria ou qualquer trilha legal. |
| 6 | Tempo | Todo instante é `TIMESTAMPTZ`. Data civil é `DATE`. Hora do dia é `TIME`. |
| 7 | Duração | **Sempre `INTEGER` em minutos**, nunca `float`, `interval` ou "horas decimais". A conversão para decimal é da camada de apresentação. |
| 8 | Dinheiro | `NUMERIC(14,2)`. Fatores e multiplicadores: `NUMERIC(6,4)`. |
| 9 | Binários | Nunca no banco. `*_ref` guarda a chave do objeto no MinIO; `hash_sha256` guarda a prova de integridade. Exceção única: `biometria_templates.template_cifrado`, que é `BYTEA` porque precisa da mesma transação da credencial. |
| 10 | Multi-tenant | `tenant_id UUID NOT NULL` em toda tabela de domínio, sempre **na primeira posição** dos índices compostos, com RLS habilitada e forçada. |
| 11 | Prefixos | `uq_` unique, `ix_` índice, `ck_` check, `fk_` chave estrangeira, `ex_` exclusion, `pol_` policy, `trg_` trigger, `fn_` função, `dom_` domínio. |

### 1.1 Isolamento por Row Level Security

Toda tabela com `tenant_id` recebe:

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE  ROW LEVEL SECURITY;
CREATE POLICY pol_isolamento_tenant ON <t>
    USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

A aplicação executa `SET LOCAL app.tenant_id = '<uuid>'` no início de cada transação.
**Sem esse `SET`, `current_setting` devolve `NULL` e nenhuma linha é visível** — falha
fechada, não aberta. O acesso cross-tenant do suporte da SEEG é feito pela role
`ponto_suporte`, que tem `BYPASSRLS` e **não tem `SELECT` em `biometria_templates`**;
nunca por brecha na policy.

As três instruções são emitidas por um laço sobre o catálogo (`schema.sql`, seção 19)
em vez de escritas à mão tabela a tabela. Motivo: o laço garante cobertura de 100 % por
construção, e o bloco de verificação da seção 21 **aborta a migração** se alguma tabela
com `tenant_id` ficar sem RLS, sem `FORCE` ou sem policy. Escrever à mão 92 vezes
convida ao esquecimento silencioso, que é exatamente a falha que não podemos ter.

### 1.2 Imutabilidade

| Tabela | Regra | Como é imposta |
|---|---|---|
| `marcacoes` (+ partições) | Nem UPDATE, nem DELETE, nem TRUNCATE | Gatilho `fn_registro_imutavel` + `REVOKE` para `ponto_app` |
| `nsr_emissoes`, `marcacao_idempotencia`, `comprovantes` | idem | idem |
| `auditoria`, `acessos_dados_sensiveis` | idem | idem |
| `assinaturas_espelho` | idem | idem |
| `terminal_saude` | idem (série temporal) | `REVOKE` |
| `bh_lancamentos` | Só `consumido_minutos` pode mudar | Gatilho `fn_bh_lancamento_imutavel` + `GRANT UPDATE (consumido_minutos)` |
| `arquivo_assinaturas` | Sem DELETE; UPDATE só para o resultado da validação | Gatilho de DELETE + `REVOKE DELETE` |

Defesa em profundidade: mesmo que um bug da aplicação tente `UPDATE marcacoes`, o gatilho
aborta; mesmo que alguém desative o gatilho, a role não tem o privilégio.

---

## 2. Glossário

Ordem alfabética. Formato: **Termo** — *(tabela: `x`)* — definição.

**Abono** — *(tabelas: `tipos_tratamento`, `tratamentos`, `tipos_afastamento`)* —
Ato de justificar uma ausência ou um atraso de modo que ele deixe de gerar débito na
apuração, sempre com autor, motivo e, quando exigido, documento anexo.

**Adicional noturno** — *(colunas: `apuracoes_dia.noturno_minutos`, `jornadas.noturno_inicio/noturno_fim`)* —
Acréscimo devido pelo trabalho prestado no período noturno (padrão urbano 22h–05h),
configurável por jornada porque a regra rural tem faixa diferente.

**AEJ (Arquivo Eletrônico de Jornada)** — *(tabela: `aej_arquivos`)* —
Arquivo gerado pelo **Programa de Tratamento** contendo vínculos, horário contratual,
marcações, ausências, banco de horas e identificação do PTRP; substitui os antigos
AFDT e ACJEF e é onde as correções legitimamente aparecem.

**AFD (Arquivo Fonte de Dados)** — *(tabela: `afd_arquivos`)* —
Arquivo gerado **exclusivamente pelo REP-P**, em ASCII ISO 8859-1 com campos separados
por `|` e linhas em CR+LF, contendo as marcações originais com NSR e CRC-16 por registro
e SHA-256 do arquivo — **nenhum tratamento entra aqui**.

**Afastamento** — *(tabelas: `afastamentos`, `tipos_afastamento`)* —
Período de ausência legítima do colaborador (férias, atestado, licença, INSS, suspensão)
que entra na apuração como insumo e é exportado no bloco de ausências do AEJ.

**Allowlist CIDR** — *(tabela: `redes_permitidas`)* —
Conjunto de faixas de IP (IPv4 e IPv6) a partir das quais a empresa ou a unidade autoriza
o registro de ponto, tipicamente usada para restringir o canal web à rede corporativa.

**Apuração** — *(tabelas: `apuracoes_dia`, `apuracao_componentes`)* —
Resultado do cálculo de um dia para um vínculo, derivado de marcações + tratamentos +
regras da jornada vigente, sempre recalculável e determinístico.

**Attestation** — *(colunas: `dispositivos.attestation_status`, `marcacoes_meta.attestation_veredito`)* —
Veredito de integridade da plataforma (Play Integrity no Android, App Attest e DeviceCheck
no iOS) sobre o aparelho e o app, **verificado no servidor e nunca no cliente**.

**Banco de horas** — *(tabelas: `bh_politicas`, `bh_contas`, `bh_lancamentos`, `bh_saldos`, `bh_quitacoes`)* —
Regime de compensação em que o saldo de jornada de cada dia é acumulado numa conta-corrente
de horas, com prazo legal de compensação de até 6 meses (acordo individual escrito) ou até
12 meses (acordo ou convenção coletiva).

**Biometria / template biométrico** — *(tabelas: `biometrias`, `biometria_templates`)* —
Vetor de características faciais **cifrado em repouso** com chave gerenciada fora do banco,
versionado por modelo para permitir troca de motor sem recadastro geral; é dado pessoal
sensível pela LGPD e nunca é a imagem original.

**Canal** — *(coluna: `marcacoes.canal`)* —
Meio pelo qual a marcação entrou no sistema: `terminal`, `mobile`, `web`, `totem`, `api`
ou `importacao` — dimensão obrigatória de todo relatório de uso e de toda regra antifraude.

**Catch-up** — *(coluna: `terminais.ultimo_log_externo_id`)* —
Recuperação dos registros acumulados num coletor enquanto a rede esteve fora, feita por
marca d'água do último `access_log` coletado, garantindo que nada se perca e nada duplique.

**Coletor** — *(tabelas: `terminais`, `dispositivos`)* —
Equipamento ou aplicativo que **identifica a pessoa e captura o evento** (iDFace, celular,
navegador, totem) — o coletor **não é o REP-P** e não atribui NSR.

**Colaborador** — *(tabela: `colaboradores`)* —
A pessoa física que trabalha, com seus dados cadastrais; as condições de trabalho vivem
em `contratos` e `vinculos`.

**Compensação** — *(tabelas: `bh_lancamentos`, `solicitacoes`)* —
Uso de saldo credor de banco de horas para cobrir ausência ou folga, podendo ser programada
com antecedência e consumindo saldo previamente reservado.

**Comprovante de registro** — *(tabela: `comprovantes`)* —
Documento emitido a cada marcação contendo NSR, CPF, data/hora e hash; a impressão no ato
é dispensada porque o sistema garante acesso eletrônico permanente, com as **últimas 48 h**
sempre disponíveis em app e web.

**Consentimento** — *(tabela: `consentimentos`)* —
Autorização versionada e datada do titular para tratamento de dado sensível; o registro de
ponto se apoia em obrigação legal, mas a **biometria exige consentimento específico**.

**Contrato** — *(tabela: `contratos`)* —
O instrumento jurídico entre colaborador e empresa (tipo de contratação, cargo, remuneração,
carga contratada, vigência) — distinto de **vínculo**, que é o objeto usado pelo motor.

**CRC-16** — *(coluna: `marcacoes.crc16`)* —
Código de redundância cíclica de 16 bits calculado por registro conforme o leiaute do AFD,
congelado no momento da gravação.

**Crédito** — *(coluna: `bh_lancamentos.tipo = 'credito'`)* —
Lançamento que aumenta o saldo do banco de horas, originado de saldo positivo da apuração
do dia e sujeito ao fator da política (por exemplo 1,5 para hora extra a 50 %).

**Débito** — *(coluna: `bh_lancamentos.tipo = 'debito'`)* —
Lançamento que reduz o saldo do banco de horas, originado de saldo negativo do dia,
de folga compensada ou de quitação.

**Delegação** — *(tabela: `delegacoes`)* —
Transferência temporária das atribuições de aprovação de um usuário para outro (caso típico:
férias do gestor), com janela de vigência e registro na auditoria de toda ação exercida por ela.

**Dispositivo** — *(tabela: `dispositivos`)* —
Aparelho registrado que pode originar marcação, com seu estado antifraude conhecido;
regra de negócio: **um dispositivo ativo por colaborador**, e a troca exige aprovação do RH.

**DSR (Descanso Semanal Remunerado)** — *(colunas: `apuracoes_dia.dsr_credito_minutos`, `dsr_debito_minutos`; `jornada_dias.tipo_dia = 'dsr'`)* —
Repouso semanal remunerado, que muda o fator da hora extra quando trabalhado e é perdido
por falta injustificada na semana.

**Empresa** — *(tabela: `empresas`)* —
Pessoa jurídica empregadora dentro do tenant; matriz e filiais são linhas distintas ligadas
por `matriz_id`, cada uma com CNPJ próprio e arquivos fiscais próprios.

**Escala** — *(tabelas: `escalas`, `escala_ciclos`, `escala_atribuicoes`)* —
Padrão cíclico de trabalho e folga (5x2, 6x1, 4x2, 12x36, espanhola, rotativa de N dias)
resolvido por aritmética modular a partir de uma data-âncora, sem materializar calendário.

**Espelho de ponto** — *(tabelas: `espelhos`, `assinaturas_espelho`)* —
Demonstrativo da jornada apurada de um vínculo num período; o tipo `previo` circula durante
a conferência e o tipo `oficial` é emitido no fechamento e assinado pelo colaborador.

**Expiração** — *(coluna: `bh_lancamentos.tipo = 'expiracao'`; `bh_politicas.acao_vencimento`)* —
Perda de horas credoras que atingiram o fim do período de compensação sem terem sido
compensadas nem quitadas — sempre registrada, nunca silenciosa.

**Fechamento** — *(tabelas: `periodos`, `fechamentos`)* —
Trava do período para um escopo, após a qual a apuração não recalcula; a reabertura é
**sempre nominal e justificada**, garantido por `CHECK` no banco.

**Feriado** — *(tabelas: `feriado_conjuntos`, `feriados`, `unidade_feriado_conjuntos`)* —
Dia de suspensão do expediente, nacional, estadual, municipal ou próprio da empresa, podendo
ser fixo ou móvel (calculado a partir da Páscoa) e integral ou de expediente reduzido.

**Fila offline** — *(tabela: `fila_offline`)* —
Estágio anterior à marcação, onde ficam os itens capturados sem rede — cifrados, assinados
por HMAC e numerados por contador monotônico anti-replay, com TTL padrão de 72 h.

**Geocerca** — *(colunas: `unidades.geocerca_*`; `marcacoes_meta.dentro_geocerca`)* —
Perímetro geográfico da unidade, definido por ponto central mais raio **ou** por polígono
GeoJSON (o polígono tem precedência), dentro do qual o registro por app é considerado válido.

**Hash chain (trilha encadeada)** — *(colunas: `auditoria.hash_anterior/hash_registro`, `marcacoes.hash_anterior/hash_registro`, `bh_lancamentos.hash_anterior/hash_registro`)* —
Encadeamento em que cada registro carrega o hash do anterior, de modo que a remoção
silenciosa de uma linha quebra a cadeia e se torna detectável.

**Hora ficta** — *(coluna: `jornadas.hora_ficta_noturna`; `apuracoes_dia.noturno_ficta_minutos`)* —
Hora noturna urbana reduzida de 52 minutos e 30 segundos, que faz 60 minutos de relógio no
período noturno valerem mais de uma hora de jornada.

**Horário** — *(tabela: `horarios`)* —
Gabarito reutilizável de entrada, saída e intervalos previstos de um dia de trabalho; é o
bloco de montagem de jornadas e turnos.

**Idempotência** — *(tabela: `marcacao_idempotencia`)* —
Garantia de que reenviar o mesmo registro não cria duplicata, imposta por três chaves:
`external_id` (canal API), `dispositivo_id + log_externo_id` (catch-up de terminal) e
`Idempotency-Key` (cabeçalho HTTP).

**Interjornada** — *(colunas: `jornadas.interjornada_minima_minutos`, `apuracoes_dia.interjornada_violada`)* —
Intervalo entre o fim de uma jornada e o início da seguinte, com mínimo legal de 11 horas
cuja violação gera **ocorrência**, não correção automática.

**Intrajornada** — *(colunas: `jornadas.intervalo_minimo_minutos`, `apuracoes_dia.intrajornada_suprimida_minutos`)* —
Intervalo de descanso e alimentação dentro da jornada, cuja supressão total ou parcial gera
indenização de 50 % do período suprimido (art. 71, § 4º da CLT) e ocorrência no relatório.

**Jornada** — *(tabelas: `jornadas`, `jornada_dias`, `vinculo_jornadas`)* —
Conjunto de regras de trabalho e de cálculo aplicado a um vínculo (carga, tolerâncias,
tratamento do noturno, limites de extra, política de intervalo), versionado por vigência.

**Liveness (prova de vida)** — *(colunas: `marcacoes_meta.liveness_aprovado`, `liveness_metodo`)* —
Verificação de que a face capturada pertence a uma pessoa presente e viva, por desafio ativo
(piscar, virar a cabeça) e análise passiva de textura, para reprovar foto impressa,
vídeo em tela e máscara.

**Marcação** — *(tabela: `marcacoes`)* —
O registro de ponto propriamente dito: **imutável, append-only e particionado por mês**,
com NSR próprio, CRC-16 e hash encadeado — nenhum endpoint, tela ou rotina o altera ou apaga.

**Matrícula eSocial** — *(coluna: `vinculos.matricula_esocial`)* —
Identificador do vínculo no eSocial, exigido no registro de vínculo do AEJ e único por empresa;
não confundir com `colaboradores.matricula`, que é a matrícula interna usada no terminal.

**Mock location** — *(coluna: `marcacoes_meta.mock_location`)* —
Indicação de que a posição informada veio de provedor simulado (app de fake GPS), tratada
conforme a política configurada em `politicas_registro`.

**NSR (Número Sequencial de Registro)** — *(coluna: `marcacoes.nsr`; tabelas `nsr_sequencias`, `nsr_emissoes`)* —
Numeração sequencial por REP-P que começa em 1 e **não admite lacuna nem reuso**, inclusive
para marcações que chegam offline dias depois; é alocada transacionalmente, nunca por
`SEQUENCE` do PostgreSQL — sequence não volta atrás em rollback e produziria buraco.

**Ocorrência** — *(tabela: `ocorrencias`)* —
Inconsistência ou desvio detectado pelo motor (marcação ímpar, falta, extra excedida, fora
de cerca, score baixo) que **chama o humano em vez de corrigir sozinho**.

**Pausa NR-17** — *(colunas: `horarios.intervalos_extras`, `apuracoes_dia.pausas_nr17_minutos`)* —
Pausa obrigatória para atividades de digitação e teleatendimento, contada automaticamente
e distinta do intervalo intrajornada.

**Perfil e permissão** — *(tabelas: `perfis`, `permissoes`, `perfil_permissoes`, `usuario_perfis`)* —
Papel do RBAC e a autorização granular por recurso e ação; a atribuição de perfil ao usuário
sempre carrega **escopo** (tenant, empresa, unidade, departamento, equipe ou próprio).

**Período** — *(tabela: `periodos`)* —
Janela de apuração da empresa (mensal, quinzenal, semanal ou própria do banco de horas);
o período do ponto e o do banco de horas são independentes.

**Prontidão** — *(coluna: `apuracoes_dia.prontidao_minutos`; `turnos.tipo`)* —
Tempo em que o empregado permanece nas dependências da empresa aguardando ordens, remunerado
por fator próprio, distinto de sobreaviso.

**PTRP (Programa de Tratamento de Registro de Ponto)** — *(colunas: `aej_arquivos.ptrp_*`)* —
O software que trata os registros e gera o AEJ; no nosso caso é o mesmo produto que atua como
REP-P, mas as duas funções são **deliberadamente separadas no modelo** — o REP-P gera AFD,
o PTRP gera AEJ.

**Quitação** — *(tabela: `bh_quitacoes`)* —
Liquidação de saldo de banco de horas por pagamento em folha, folga, acerto de rescisão ou
expiração, sempre gerando lançamento correspondente no extrato.

**REP-P (Registrador Eletrônico de Ponto via Programa)** — *(tabela: `rep_ps`)* —
O **nosso software**, registrado no INPI, que recebe o evento do coletor, atribui NSR, calcula
CRC-16, grava a marcação e gera o AFD — o terminal facial não é o REP-P.

**Score de confiança** — *(colunas: `marcacoes_meta.score_confianca`, `classificacao_confianca`; tabela `politicas_registro`)* —
Nota de 0 a 100 composta no servidor a partir de attestation, RASP, modo desenvolvedor, mock
location, coerência geográfica, velocidade implícita e reputação do dispositivo, comparada
com limiares configuráveis que decidem entre **bloquear, sinalizar para revisão ou aceitar**.

**Sobreaviso** — *(coluna: `apuracoes_dia.sobreaviso_minutos`; `turnos.tipo`)* —
Tempo em que o empregado permanece à disposição fora do local de trabalho aguardando
chamado, remunerado por fator próprio e passível de conta de banco de horas separada.

**Soft delete** — *(colunas: `excluido_em`, `excluido_por`)* —
Marcação lógica de exclusão usada **apenas em cadastros**, que preserva o histórico e mantém
a integridade referencial de marcações e apurações antigas.

**Tenant** — *(tabelas: `tenants`, `tenant_configuracoes`)* —
Cliente do SaaS e raiz do isolamento: todo dado de domínio nasce com `tenant_id` e é filtrado
por RLS no PostgreSQL além do filtro da aplicação; um tenant contém uma ou mais empresas.

**Tolerância** — *(colunas: `jornadas.tolerancia_marcacao_minutos`, `tolerancia_diaria_minutos`, `descontar_tudo_se_exceder`)* —
Margem em que a diferença entre horário previsto e marcado não gera efeito no cálculo:
até 5 minutos por marcação e 10 minutos no total do dia (art. 58, § 1º da CLT), configurável.

**Tratamento** — *(tabelas: `tipos_tratamento`, `tratamentos`)* —
A **única** forma de corrigir a jornada: uma camada que se soma à marcação na apuração sem
jamais alterá-la, sempre com autor, data, motivo e anexo — vai para o AEJ e nunca para o AFD.

**Turno** — *(tabela: `turnos`)* —
Faixa nomeada de trabalho materializada por um horário (manhã, tarde, noite), com posição
de sequência quando há revezamento.

**Unidade** — *(tabela: `unidades`)* —
Local físico de trabalho de uma empresa, que carrega o **fuso horário efetivo da apuração**,
a geocerca do registro por app e o conjunto de feriados aplicável.

**Usuário** — *(tabela: `usuarios`)* —
Identidade de acesso ao sistema, distinta de colaborador: quem só bate ponto no terminal não
precisa de usuário, e nem todo usuário é colaborador (suporte da SEEG, contas de integração).

**Vínculo** — *(tabela: `vinculos`)* —
A relação de trabalho efetiva, na granularidade que o AEJ e o eSocial exigem — **é a chave de
apuração**: apuração do dia, escala, jornada vigente e conta de banco de horas penduram no
vínculo, não no colaborador, que pode ter vínculos simultâneos.

**Webhook** — *(tabelas: `webhooks`, `webhook_entregas`)* —
Notificação HTTP assinada em HMAC enviada ao integrador quando um evento do catálogo
`events.yaml` ocorre, com retentativa exponencial e fila de mortos (DLQ).

---

## 3. Divergências em relação aos nomes de tabela sugeridos

O enunciado da Fase 0 apresentou os grupos de tabelas como **sugestão**, autorizando ajuste
com razão clara documentada. Todos os nomes sugeridos foram mantidos. As divergências abaixo
são **acréscimos** e **decisões estruturais**, nenhuma renomeação.

### 3.1 Tabelas acrescentadas (7)

| Tabela | Grupo | Por que existe |
|---|---|---|
| `nsr_emissoes` | 7 · Marcação | **Restrição real do PostgreSQL:** uma constraint `UNIQUE` em tabela particionada precisa conter a chave de partição. `UNIQUE (tenant_id, rep_p_id, nsr)` pedida no enunciado é, portanto, **impossível** em `marcacoes`, que é particionada por `datahora_marcacao`. Em `marcacoes` a constraint foi criada com a chave de partição incluída (unicidade dentro do mês), e esta tabela **não particionada** impõe a unicidade global e transforma a detecção de lacuna em uma consulta trivial. Sem ela, dois NSR iguais em meses diferentes passariam. |
| `marcacao_idempotencia` | 7 · Marcação | Mesmo motivo. Os índices `(tenant_id, canal, external_id)` e `(tenant_id, dispositivo_id, log_externo_id)` foram criados em `marcacoes` conforme pedido, mas servem para **consulta**; só uma tabela não particionada consegue **impor** unicidade entre meses. É o que faz o reenvio tardio de um item offline colidir em vez de duplicar marcação. |
| `politicas_registro` | 7 · Marcação | O PROJETO define política configurável por empresa entre **bloquear, sinalizar e permitir** para modo desenvolvedor, root, mock location e fora de cerca, além dos limiares do score de confiança. Sem tabela própria, essa decisão viraria JSON solto em configuração, sem `CHECK` e sem consulta indexada — e é ela que a F5, a F8 e a F14 leem em todo registro. |
| `redes_permitidas` | 3 · Organização | O enunciado colocou "allowlist CIDR" como atributo de `unidades`. Uma empresa tem **múltiplos links** (matriz, filial, VPN, 4G corporativo) e a allowlist também precisa existir em nível de empresa. Uma coluna de array perderia `CHECK`, índice e vigência por canal; a tabela filha resolve os três. |
| `unidade_feriado_conjuntos` | 6 · Jornada | Uma unidade precisa somar **nacional + estadual + municipal** simultaneamente. Uma FK simples `unidades.feriado_conjunto_id` só permitiria um conjunto por unidade, quebrando o requisito de feriado municipal aplicar só na unidade certa. Relação N:N é a modelagem correta. |
| `vinculo_jornadas` | 6 · Jornada | O PROJETO exige "jornada vigente com histórico" e a F3 exige que "troca de jornada no meio do mês respeite vigência". Guardar `jornada_id` direto no vínculo reescreveria o passado a cada troca. Esta tabela guarda a vigência com constraint `EXCLUDE` que impede sobreposição. É o par simétrico de `escala_atribuicoes`, que o enunciado já previa. |
| `horarios` | 6 · Jornada | O enunciado lista `turnos` e `horarios` como tabelas separadas — mantidas as duas. Registrado aqui só para deixar explícita a separação: **`horarios` é o gabarito** (entrada, saída, intervalos, carga) e **`turnos` é o gabarito nomeado e sequenciado** para revezamento. Um horário serve a vários turnos e a vários dias de jornada. |

### 3.2 Decisões estruturais que merecem registro

**`contratos` × `vinculos` — a distinção.**
O enunciado lista as duas tabelas sem definir a fronteira, e sem fronteira elas viram
duplicata. Adotado: **`contratos` é o instrumento jurídico** (tipo de contratação, cargo,
salário, carga contratada, cláusula do art. 62, vigência); **`vinculos` é a relação de
trabalho operacional** na granularidade do eSocial e do AEJ (matrícula eSocial, categoria,
unidade, jornada vigente, conta de banco de horas). Um contrato origina um vínculo; um
colaborador pode ter vínculos simultâneos em empresas diferentes do mesmo tenant, impedido
de sobrepor na mesma empresa por constraint `EXCLUDE`. **Todo o motor de apuração pendura
em `vinculo_id`, nunca em `colaborador_id`.**

**`marcacoes.tipo_registro` × `marcacoes.sentido_informado`.**
O enunciado pede `tipo_registro`. No leiaute do AFD, "tipo de registro" é o tipo da **linha
do arquivo** (`7` é a marcação de ponto do REP-P), não entrada ou saída. O REP-P
legalmente **não registra sentido** — o pareamento é feito na apuração. Modelado então:
`tipo_registro` com o significado do leiaute, e `sentido_informado` (anulável) para quando
o coletor informa espontaneamente, como faz o iDFace. **Proibido preencher `sentido_informado`
por inferência no momento da gravação**: sequência ímpar é inconsistência sinalizada, não
corrigida silenciosamente.

**`permissoes` sem `tenant_id`.**
Exceção consciente à regra "toda tabela de domínio tem `tenant_id`". As permissões são o
catálogo de recursos e ações do **código** (`marcacoes.ler`, `fechamentos.reabrir`), idênticas
em todos os tenants e somente leitura para a aplicação. Replicá-las por tenant criaria N cópias
que precisariam ser migradas em conjunto a cada endpoint novo, com risco de divergência.
Fica sem RLS, com `REVOKE INSERT, UPDATE, DELETE` para `ponto_app`. O que é por tenant são
`perfis`, `perfil_permissoes` e `usuario_perfis` — todos com `tenant_id` e RLS.

**`tenants` isolada por `id`.**
A raiz não tem `tenant_id` porque ela **é** o tenant. RLS declarada explicitamente com a
policy sobre `id`. Como o login precisa resolver o tenant pelo subdomínio antes de existir
`app.tenant_id`, existe `fn_resolve_tenant(slug)` em `SECURITY DEFINER`, expondo apenas
quatro colunas — não há como enumerar a base de clientes por ela.

**`criado_por` e `atualizado_por` sem chave estrangeira.**
Decisão uniforme nas 92 tabelas: são referências lógicas a `usuarios.id`, sem FK. Três razões:
(a) evita ciclo entre `tenants`, `usuarios` e `colaboradores` na criação do schema; (b) preserva
a autoria em registros legais mesmo depois do expurgo LGPD do usuário; (c) permite autoria de
processos que não são usuários (worker, migração, importador). A resolução para nome é feita
na aplicação, com fallback para "sistema".

**Referências polimórficas em `anexos` e `arquivo_assinaturas`.**
Ambas usam `entidade` + `entidade_id` (ou `tipo_arquivo` + `arquivo_id`) **sem FK**, porque
apontam para tabelas diferentes conforme o caso. O conjunto de alvos é fechado por `CHECK`,
o que impede referência a tabela inexistente. Integridade referencial é responsabilidade da
aplicação — divergência deliberada, registrada aqui para que nenhuma fase a "conserte" por
engano.

**`marcacoes_meta` não é particionada.**
`marcacoes` é particionada por mês; `marcacoes_meta` não. A FK é composta
`(marcacao_id, marcacao_datahora) → marcacoes (id, datahora_marcacao)`, exigência do
PostgreSQL para referenciar tabela particionada. Motivo de não particionar: `marcacoes_meta`
é **mutável** (o gestor revisa o score, os campos `revisao_*` mudam) e é sempre acessada por
`marcacao_id`, não por faixa de data. Pode ser particionada depois sem mudança de contrato.

**Partição `marcacoes_default`.**
Existe como rede de segurança: **nenhuma marcação legítima pode ser recusada por falta de
partição**. Linha nela é alarme operacional, não normalidade — o scheduler cria as partições
com antecedência via `fn_cria_particao_marcacoes(DATE)`, que já cria a partição com RLS,
policy, barreira de `TRUNCATE` e privilégios corretos. Fronteiras de partição usam offset
fixo `-03` (o Brasil não tem horário de verão desde 2019), o que as torna determinísticas.

**`tipos_tratamento.afeta_afd` com `CHECK (afeta_afd = FALSE)`.**
A coluna existe apenas para tornar a regra legal explícita e auditável no próprio schema.
Nenhum tratamento, de nenhum tipo, jamais entra no AFD. Não é configuração.

**`Comprovante.datahoraMarcacao` (API) × `comprovantes.marcacao_datahora` (banco).**
Divergência de nomenclatura **deliberadamente mantida** — decisão do orquestrador em
[RFC-001 D-07](../../docs/rfc/RFC-001-divergencias-fase-0.md), 25/07/2026. O `openapi.yaml`
expõe a propriedade como `datahoraMarcacao`; a coluna correspondente em `schema.sql` é
`comprovantes.marcacao_datahora`, com a ordem das palavras invertida. As duas pontas são
internamente consistentes e nada quebra, mas **este é o único campo do contrato em que a
conversão camelCase → snake_case não é mecânica**: `datahoraMarcacao` traduzido
automaticamente daria `datahora_marcacao`, que é o nome da coluna em `marcacoes`, **não**
o da coluna em `comprovantes`. Quem escrever serialização, mapeamento ORM ou gerador de
código para `comprovantes` precisa tratar este par explicitamente. Corrigir exigiria
alterar `openapi.yaml` **ou** `schema.sql`, ambos congelados; o custo de mexer em contrato
congelado por questão cosmética é maior que o benefício.

---

## 4. Mapa das tabelas (92)

| Grupo | Tabelas |
|---|---|
| 1 · Tenancy (2) | `tenants`, `tenant_configuracoes` |
| 2 · Organização (6) | `empresas`, `unidades`, `redes_permitidas`, `departamentos`, `centros_custo`, `cargos` |
| 3 · Identidade e RBAC (10) | `usuarios`, `credenciais`, `sessoes`, `refresh_tokens`, `mfa_dispositivos`, `perfis`, `permissoes`, `perfil_permissoes`, `usuario_perfis`, `delegacoes` |
| 4 · Pessoas (7) | `colaboradores`, `contratos`, `vinculos`, `colaborador_gestores`, `equipes`, `equipe_membros`, `documentos` |
| 5 · Biometria e dispositivos (6) | `biometrias`, `biometria_templates`, `dispositivos`, `dispositivo_vinculos`, `terminais`, `terminal_saude` |
| 6 · Jornada e calendário (13) | `horarios`, `jornadas`, `jornada_dias`, `turnos`, `escalas`, `escala_ciclos`, `escala_atribuicoes`, `vinculo_jornadas`, `feriado_conjuntos`, `feriados`, `unidade_feriado_conjuntos`, `tipos_afastamento`, `afastamentos` |
| 7 · Marcação (9) | `rep_ps`, `nsr_sequencias`, `marcacoes`, `nsr_emissoes`, `marcacao_idempotencia`, `marcacoes_meta`, `fila_offline`, `comprovantes`, `politicas_registro` |
| 8 · Tratamento e apuração (5) | `tipos_tratamento`, `tratamentos`, `apuracoes_dia`, `apuracao_componentes`, `ocorrencias` |
| 9 · Banco de horas (5) | `bh_politicas`, `bh_contas`, `bh_lancamentos`, `bh_saldos`, `bh_quitacoes` |
| 10 · Workflow (6) | `tipos_solicitacao`, `solicitacoes`, `aprovacoes`, `anexos`, `notificacoes`, `notificacao_preferencias` |
| 11 · Fechamento (4) | `periodos`, `fechamentos`, `espelhos`, `assinaturas_espelho` |
| 12 · Fiscal (3) | `afd_arquivos`, `aej_arquivos`, `arquivo_assinaturas` |
| 13 · Integração (7) | `api_clients`, `api_keys`, `oauth_tokens`, `webhooks`, `webhook_entregas`, `integracoes_folha`, `importacoes` |
| 14 · Auditoria e LGPD (5) | `auditoria`, `acessos_dados_sensiveis`, `consentimentos`, `politicas_retencao`, `solicitacoes_titular` |
| 15 · Relatórios (4) | `relatorio_definicoes`, `relatorio_agendamentos`, `relatorio_execucoes`, `preferencias_colunas` |

Mais 24 partições mensais de `marcacoes` (2026-01 a 2027-12) e a partição `marcacoes_default`.

---

## 5. Sequência canônica do motor

Decorar esta ordem evita 90 % dos erros de escopo entre fases:

```
marcações imutáveis
      ↓
regras da jornada vigente do dia  (jornadas · jornada_dias · escalas · feriados)
      ↓
tratamentos aplicáveis            (ajustes aprovados · abonos · afastamentos)
      ↓
apuração do dia                   (apuracoes_dia · apuracao_componentes · ocorrencias)
      ↓
lançamentos de banco de horas     (bh_lancamentos)
      ↓
fechamento                        (fechamentos · espelhos · assinaturas_espelho)
      ↓
arquivos fiscais                  (AFD ← marcações · AEJ ← apuração e tratamentos)
```

Duas leituras obrigatórias desse diagrama:

1. **A seta nunca aponta para trás.** Nada abaixo escreve em `marcacoes`.
2. **O AFD deriva só do topo.** O AEJ é quem enxerga tratamento. Confundir os dois é o
   erro que invalida o sistema numa fiscalização.

---

## 6. Termos proibidos

Palavras que **não** devem aparecer em código, API, interface ou documentação, com o termo
correto ao lado — evitam sinônimo divergente entre fases.

| Não usar | Usar |
|---|---|
| batida, ponto batido, registro de ponto (como entidade) | **marcação** |
| ajuste, correção, edição de marcação | **tratamento** |
| cálculo, processamento do dia | **apuração** |
| horário de trabalho (como regra) | **jornada** |
| banco de horas negativo / positivo (como entidade) | **saldo devedor / saldo credor** |
| funcionário, empregado (no código) | **colaborador** (pessoa) ou **vínculo** (relação) |
| empresa (quando se quer dizer cliente do SaaS) | **tenant** |
| relógio de ponto, catraca (como REP) | **coletor** (o REP-P é o software) |
| deletar marcação | não existe — **desconsiderar via tratamento** |
