# F01 / A2 — Prova de que a policy de RLS, se quebrada, faz o teste falhar

Exigido pelo PCF da fase (T3, "Pronto quando"): "os testes ... passam a falhar
se a policy de uma tabela for removida a mao (prove isso uma vez e cole a
saida no relatorio)". Este documento é essa prova, executada uma única vez
contra o PostgreSQL 16 real de teste (`ponto_f1_a2`, o mesmo banco usado pela
suíte `tests/f1`), conectado como o usuário administrativo (superusuário
`ponto` nesta instância de teste — o único capaz de `DROP POLICY`/`ALTER
POLICY`; os testes em si sempre rodam como a role de LOGIN não-superusuário
`ponto_teste_f1_a2`, nunca como `ponto`).

Duas variantes, porque uma policy pode "quebrar" de duas formas distintas:

1. **Policy removida** (`DROP POLICY`): com `FORCE ROW LEVEL SECURITY` ligado
   e nenhuma policy remanescente, o Postgres nega TODO acesso à tabela (nem
   leitura nem escrita) — a tabela vira, na prática, inacessível para a role
   sem `BYPASSRLS`. O sintoma nos testes não é uma falha de asserção, é a
   própria fixture (`contexto_f1`, que semeia `usuarios` para tenant-a e
   tenant-b) não conseguir terminar de semear — todo teste do módulo termina
   em `ERROR`, não em `PASSED`.
2. **Policy presente mas com a condição errada** (`ALTER POLICY ... USING
   (true)`): a tabela continua acessível, mas a condição de isolamento deixa
   de existir. Este é o caso mais perigoso na prática (um erro de digitação
   na cláusula `USING`, não a ausência da policy) e é o que prova que os
   testes **detectam vazamento real de dado**, não só "tabela inacessível".

Ambas variantes foram executadas contra a tabela `usuarios`, alvo de
`tests/f1/tenancy/test_isolamento.py`.

## 0. Estado antes de qualquer mudança (baseline verde)

```
$ pytest tests/f1/tenancy -q
.....................                                                    [100%]
21 passed
```

Definição da policy antes de qualquer alteração (`pg_policies`):

```
policyname: pol_isolamento_tenant
cmd: ALL
qual:       (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)
with_check: (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)
```

## 1. Variante A — `DROP POLICY pol_isolamento_tenant ON usuarios`

Comando (conectado como `ponto`, o administrador da instância de teste):

```sql
DROP POLICY pol_isolamento_tenant ON usuarios;
```

Saída real de `pytest tests/f1/tenancy/test_isolamento.py tests/f1/tenancy/test_catalogo_rls.py -q`
logo em seguida:

```
ERROR tests/f1/tenancy/test_isolamento.py::test_lista_de_tabelas_cobre_pelo_menos_dez
ERROR tests/f1/tenancy/test_isolamento.py::test_sql_direto_nao_ve_linha_do_outro_tenant_em_10_tabelas
ERROR tests/f1/tenancy/test_isolamento.py::test_sql_direto_so_ve_as_proprias_linhas_por_tabela
ERROR tests/f1/tenancy/test_isolamento.py::test_sql_direto_sem_filtro_de_tenant_id_devolve_so_o_proprio_tenant
ERROR tests/f1/tenancy/test_isolamento.py::test_orm_sem_filtro_explicito_nao_ve_usuario_do_outro_tenant
ERROR tests/f1/tenancy/test_isolamento.py::test_orm_filtrar_por_email_do_outro_tenant_devolve_vazio
ERROR tests/f1/tenancy/test_isolamento.py::test_api_obter_tenant_de_outro_tenant_nao_vaza_dado
ERROR tests/f1/tenancy/test_isolamento.py::test_api_obter_tenant_atual_nunca_devolve_dado_do_outro_tenant
ERROR tests/f1/tenancy/test_isolamento.py::test_api_atualizar_tenant_de_outro_tenant_e_recusado_sem_escrever
ERROR tests/f1/tenancy/test_isolamento.py::test_insert_com_tenant_id_de_outro_tenant_e_rejeitado_pela_policy
ERROR tests/f1/tenancy/test_catalogo_rls.py::test_toda_tabela_com_tenant_id_tem_rls_forcada_e_policy
ERROR tests/f1/tenancy/test_catalogo_rls.py::test_excecoes_sao_exatamente_tenants_e_permissoes
```

Causa raiz (capturada no traceback de qualquer um dos `ERROR`s, todos com a
mesma origem): a fixture de sessão `contexto_f1` falha ao SEMEAR `usuarios`
para `tenant-a`, porque o próprio `INSERT` administrativo passa a violar RLS:

```
sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege)
new row violates row-level security policy for table "usuarios"
[SQL: INSERT INTO usuarios (tenant_id, colaborador_id, email, ...) VALUES (...)]
[parameters: {'tenant_id': UUID('1b6c0dbb-e8aa-4752-a9d4-713afea249fd'), ...,
'email': 'admin.tenant-a@teste.f1a2.local', ...}]
```

Conclusão da variante A: **sem nenhuma policy, `FORCE ROW LEVEL SECURITY`
bloqueia TUDO** (leitura e escrita) para quem não tem `BYPASSRLS` — o efeito é
"falha fechada" no sentido mais literal, e os 21 testes do módulo deixam de
passar (viram `ERROR`, que conta como falha no código de saída do `pytest` e
no relatório).

## 2. Restauração da policy original (entre as duas variantes)

```sql
CREATE POLICY pol_isolamento_tenant ON usuarios
  USING (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)
  WITH CHECK (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid);
```

Confirmação de que o baseline verde voltou antes de seguir para a variante B:

```
$ pytest tests/f1/tenancy/test_isolamento.py tests/f1/tenancy/test_catalogo_rls.py -q
............                                                             [100%]
12 passed
```

## 3. Variante B — policy presente, mas com a condição neutralizada

Comando:

```sql
ALTER POLICY pol_isolamento_tenant ON usuarios USING (true) WITH CHECK (true);
```

Esta variante é a mais importante das duas: a policy **existe** com o nome
certo (o teste de catálogo, que só verifica presença/nome, não pega este
caso — por desenho, ver a docstring de `test_catalogo_rls.py`), mas não
isola mais nada. Saída real de
`pytest tests/f1/tenancy/test_isolamento.py tests/f1/tenancy/test_catalogo_rls.py -q`:

```
FAILED tests/f1/tenancy/test_isolamento.py::test_sql_direto_nao_ve_linha_do_outro_tenant_em_10_tabelas
FAILED tests/f1/tenancy/test_isolamento.py::test_sql_direto_sem_filtro_de_tenant_id_devolve_so_o_proprio_tenant
FAILED tests/f1/tenancy/test_isolamento.py::test_orm_sem_filtro_explicito_nao_ve_usuario_do_outro_tenant
FAILED tests/f1/tenancy/test_isolamento.py::test_orm_filtrar_por_email_do_outro_tenant_devolve_vazio
```

Falhas reais, com o UUID do usuário do tenant B efetivamente vazando para a
sessão do tenant A (não um erro de infraestrutura — uma asserção que compara
dado, quebrando porque o dado errado realmente apareceu):

```
tests/f1/tenancy/test_isolamento.py:117: in test_sql_direto_sem_filtro_de_tenant_id_devolve_so_o_proprio_tenant
    assert all(str(tid) == str(contexto_f1.tenant_a.id) for tid in linhas)
AssertionError: assert False

tests/f1/tenancy/test_isolamento.py:130: in test_orm_sem_filtro_explicito_nao_ve_usuario_do_outro_tenant
    assert contexto_f1.tenant_b.admin.id not in ids_vistos
AssertionError: assert UUID('929ce93d-eebe-4f81-a177-96036c295183') not in
  {UUID('032292cb-9df6-4b0b-a43a-77f799071db8'), ..., UUID('929ce93d-eebe-4f81-a177-96036c295183'), ...}
  # UUID('929ce93d-...') É EXATAMENTE contexto_f1.tenant_b.admin.id -- o
  # usuario do tenant B apareceu na consulta feita sob o tenant A.

tests/f1/tenancy/test_isolamento.py:144: in test_orm_filtrar_por_email_do_outro_tenant_devolve_vazio
    assert resultado is None
AssertionError: assert <Usuario id=929ce93d-eebe-4f81-a177-96036c295183> is None
  # mesmo usuario do tenant B, agora encontrado por um filtro de aplicacao
  # que NAO deveria bater sob isolamento correto.
```

Os testes de tabelas que não são `usuarios` (as outras 9 do laço de
`test_sql_direto_nao_ve_linha_do_outro_tenant_em_10_tabelas`/
`test_sql_direto_so_ve_as_proprias_linhas_por_tabela`) continuam corretamente
isolados — só `usuarios` teve a policy neutralizada — mas o laço reporta a
tabela `usuarios` como vazamento e o teste-mãe falha (`assert vazamentos ==
[]`) porque a lista deixa de estar vazia.

## 4. Restauração final e confirmação

```sql
ALTER POLICY pol_isolamento_tenant ON usuarios
  USING (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)
  WITH CHECK (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid);
```

```
$ pytest tests/f1/tenancy -q
.....................                                                    [100%]
21 passed
```

## Conclusão

* Remover a policy inteiramente **bloqueia** a tabela por completo (efeito de
  `FORCE ROW LEVEL SECURITY` sem policy: nem o próprio administrador de teste,
  sem `BYPASSRLS`, consegue semear dado) — os 21 testes do módulo passam a
  `ERROR`.
* Manter a policy mas neutralizar a condição (`USING (true)`) **vaza dado
  real** de um tenant para outro, e os testes de isolamento capturam isso como
  falha de asserção com o UUID exato do registro vazado no traceback — não
  apenas "algo quebrou", mas "o dado errado apareceu".
* Em ambos os casos, a suíte de `tests/f1/tenancy` deixa de estar verde assim
  que a policy é comprometida, e volta a ficar 21/21 assim que ela é restaurada
  à definição original de `apps/api/migrations/versions/0001_inicial.py`.
