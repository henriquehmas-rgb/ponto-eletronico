# ADR-006 — Criptografia e ciclo de vida do template biométrico (LGPD)

**Status:** Aceito · 25/07/2026
**Decisores:** SEEG — arquitetura
**Fases afetadas:** F2 (enrollment), F7 (captura no app), F14 (LGPD e hardening), F6 (terminal)

---

## Contexto

Template facial é **dado pessoal sensível** pelo art. 5º, II da LGPD. Diferente
de senha, ele não pode ser trocado: vazou, vazou para sempre. E diferente de
CPF, ele identifica a pessoa fisicamente, o que muda a natureza do dano. O
tratamento exige base legal específica — para o registro de ponto em si vale a
obrigação legal, mas **para a biometria vale consentimento específico e
destacado**, o que implica que o colaborador pode recusar e mesmo assim precisa
conseguir bater ponto.

O sistema tem três lugares onde o template pode existir: no terminal Control iD
(que guarda templates próprios), no `facial-svc` self-hosted (decisão D4, motor
próprio, sem custo por chamada e sem enviar biometria a terceiro) e na base de
dados. Há ainda a imagem de captura, que é dado ainda mais sensível que o vetor.

O risco concreto: um dump de banco — backup mal protegido, réplica de leitura
esquecida, credencial vazada, ou uma consulta legítima de suporte — não pode
resultar em biometria utilizável.

## Decisão

**Envelope encryption com chave fora do banco, vetor versionado por modelo,
imagem crua nunca persistida, e todo acesso logado.**

1. **Envelope.** O template é cifrado com **AES-256-GCM** usando uma chave de
   dados (DEK) por tenant. A DEK é cifrada por uma chave mestra (KEK) que vive
   **fora do PostgreSQL** — variável de ambiente montada por volume em `dev` e
   `hml`, cofre gerenciado em `prd`. O banco guarda apenas o texto cifrado, o
   nonce e o identificador da versão da chave. **Quem tem o dump não tem a
   chave.**
2. **Autenticação do texto cifrado.** GCM (e não CBC) porque o modo já entrega
   integridade: alterar um byte do template no banco falha a decifragem em vez de
   produzir um vetor diferente e silenciosamente errado. Os dados associados
   (AAD) incluem `tenant_id` e `colaborador_id`, o que impede transplantar o
   template de uma pessoa para outra por `UPDATE` direto.
3. **Versionamento de modelo.** `biometria_templates` guarda o identificador e a
   versão do motor que gerou o vetor. Trocar o motor facial não invalida o
   histórico: convivem versões, e o reenrollment é gradual e rastreável.
4. **Imagem crua não é persistida.** A foto da captura serve para extrair o vetor
   e é descartada. Quando a política do cliente exigir retenção da imagem para
   contestação, ela vai para o MinIO cifrada, com prazo curto configurável e
   expurgo automático — nunca como padrão.
5. **Nunca sai pela API.** O vetor não é exposto em nenhuma resposta, para
   nenhum perfil, **inclusive o super admin**. A tag `biometria` do OpenAPI
   declara isso explicitamente.
6. **Todo acesso é registrado** em `acessos_dados_sensiveis`: quem, quando, de
   onde, para qual titular e com qual finalidade.
7. **Consentimento versionado** em `consentimentos`, com o texto exato aceito.
   Revogação dispara expurgo do template e **não** apaga marcações — a guarda
   das marcações é obrigação legal e prevalece.
8. **Fallback obrigatório.** Matrícula + PIN no terminal e no totem, cartão de
   proximidade, e canal alternativo sempre disponível. Quem recusa a biometria
   registra ponto do mesmo jeito.

## Alternativas consideradas

**Template em claro, protegido só por permissão de banco e RLS.** Descartado: o
vetor de arquivo é o dado com maior potencial de dano do sistema, e permissão de
banco não protege contra backup vazado, réplica esquecida ou credencial
comprometida.

**`pgcrypto` com chave passada na query (`pgp_sym_encrypt`).** Descartado porque
a chave aparece no texto do comando e, portanto, em `pg_stat_activity`, em
`log_statement` e em qualquer captura de tráfego interno. Cifrar na aplicação
mantém a chave fora do banco por completo.

**TDE / criptografia de disco.** Protege contra roubo físico do disco e não
protege contra o cenário realista: o banco montado, o dump lógico, a consulta
autorizada. É complemento, não substituto.

**Hash irreversível do template (como se faz com senha).** Impossível: o
reconhecimento facial precisa comparar por **similaridade**, e hash destrói a
métrica de distância. É a diferença fundamental entre biometria e senha, e é
justamente por isso que biometria exige proteção maior, não menor.

**Delegar a biometria a um serviço em nuvem de terceiro.** Descartado pela
decisão D4: tira o dado do controle da SEEG, cria custo por chamada, cria
dependência de disponibilidade externa para um ato que o trabalhador precisa
executar todo dia, e amplia a superfície de responsabilidade sob a LGPD.

## Consequências

**Positivas.** Vazamento de banco não vira vazamento de biometria. A troca de
motor facial fica possível sem perder rastreabilidade. O consentimento e a
recusa passam a ser caminhos de produto testáveis, não notas de rodapé jurídicas.

**Negativas e mitigações.** (a) Perder a KEK torna todos os templates
irrecuperáveis — mitigado por custódia documentada da chave, cópia offline e
runbook de rotação na F15; e o dano é limitado porque reenrollment é possível,
diferente de perder marcações. (b) A comparação exige decifrar em memória a cada
verificação: mitigado mantendo a operação dentro do `facial-svc`, com mTLS entre
`device-gw` e `facial-svc`, e cache em memória de curta duração, nunca em disco.
(c) Rotação de chave exige recifrar a base de templates — tarefa de manutenção
com janela, prevista na F14. (d) O `AAD` amarrado a `colaborador_id` significa
que mover um colaborador entre tenants exige reenrollment; decisão aceita
conscientemente, porque o caso é raro e a alternativa enfraqueceria a proteção.
