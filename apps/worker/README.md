# apps/worker — processamento assíncrono (ARQ + Redis 7)

Dois processos saem deste mesmo pacote e da mesma imagem Docker, exatamente
como `infra/docker-compose.yml` declara:

| Serviço | Comando | Módulo |
|---|---|---|
| `worker` | `arq worker.main.WorkerSettings` | `worker/main.py` |
| `scheduler` | `arq worker.scheduler.SchedulerSettings` | `worker/scheduler.py` |

Os dois caminhos de importação são **contrato**: estão em `infra/.env.example`
(`ARQ_WORKER_SETTINGS`, `ARQ_SCHEDULER_SETTINGS`), no `command` de cada
container e no `healthcheck` (`arq --check "$ARQ_WORKER_SETTINGS"`). Renomear a
classe ou o módulo quebra os três de uma vez.

---

## Estado: Fase 0 entrega andaime

Não existe regra de negócio aqui. As oito tarefas do catálogo já têm **nome,
fila e assinatura definitivos** — o nome é contrato, porque a API enfileira por
nome e renomear tarefa com job em voo perde trabalho — e devolvem um resultado
marcado como não implementado (`PONTO-INT-005`).

| Tarefa | Fila | Fase que implementa |
|---|---|---|
| `apurar_dia` | `ponto:apuracao` | F4 |
| `recalcular_periodo` | `ponto:apuracao` | F4 |
| `gerar_afd` | `ponto:fiscal` | F12 |
| `gerar_aej` | `ponto:fiscal` | F12 |
| `executar_relatorio` | `ponto:relatorios` | F11 |
| `enviar_webhook` | `ponto:integracoes` | F13 |
| `sincronizar_terminal` | `ponto:integracoes` | F6 |
| `expurgo_lgpd` | `ponto:manutencao` | F14 |

E duas rotinas periódicas no `scheduler`, exigidas pelo catálogo de eventos
(`packages/contracts/events.yaml` declara `origem: scheduler` para ambas):

| Rotina | Cron | Evento que produzirá | Fase |
|---|---|---|---|
| `verificar_banco_horas_vencendo` | diária, 04:10 | `banco_horas.vencendo` | F4 |
| `verificar_terminal_offline` | a cada 5 min | `terminal.offline` | F6 |

---

## Estrutura

```
apps/worker/
├── Dockerfile              # multi-stage; a mesma imagem serve worker e scheduler
├── .dockerignore
├── pyproject.toml          # dependências, ruff, mypy --strict, pytest
├── README.md
├── tests/
│   └── test_andaime_worker.py
└── worker/
    ├── __init__.py
    ├── py.typed
    ├── config.py           # pydantic-settings; mesmos nomes do compose
    ├── filas.py            # nomes de fila e resultado padrão do andaime
    ├── log.py              # log estruturado JSON (mesmo formato do apps/api)
    ├── main.py             # WorkerSettings  ← ponto de entrada do `worker`
    ├── scheduler.py        # SchedulerSettings ← ponto de entrada do `scheduler`
    └── tarefas/
        ├── __init__.py     # catálogo: TAREFAS e NOMES_DAS_TAREFAS
        ├── apuracao.py
        ├── fiscal.py
        ├── integracoes.py
        ├── lgpd.py
        └── relatorios.py
```

---

## Decisões que ficam visíveis no código

**Nenhuma conexão com PostgreSQL na subida.** Igual ao `apps/api`: o processo
sobe e responde ao `arq --check` mesmo com o banco fora. Conectar no
`on_startup` transformaria indisponibilidade de dependência em *crash loop* — e
ainda tiraria do ar o único sinal que diria o que está errado.

**Worker e scheduler são processos separados.** No ARQ, `cron_jobs` rodam no
próprio processo que os declara, e não são enfileirados para outro consumir. Se
o `worker` acumulasse as duas funções, uma geração de AFD de 12 meses segurando
todas as vagas de `max_jobs` atrasaria a rotina que detecta terminal fora do ar
— justamente a rotina cuja utilidade é ser pontual.

**Chaves de saúde distintas.** `ponto:worker:health` e `ponto:scheduler:health`.
Os dois processos dividem o mesmo Redis; chave compartilhada faria o
`arq --check` de um responder pela vida do outro.

**Uma fila só na Fase 0.** `worker/filas.py` já separa as seis filas definitivas,
mas um único processo consome `ponto:padrao` enquanto nada tem custo real. A
partir da F4 basta subir réplicas apontando `ARQ_WORKER_SETTINGS` para uma
subclasse com outro `queue_name`; nenhuma linha de tarefa muda.

**Tarefa de andaime devolve, não levanta.** Exceção entraria no ciclo de
retentativa do ARQ e ficaria batendo no Redis até esgotar `max_tries`, poluindo
fila e log com falha que não é falha.

**Cron no relógio local.** `montar_cron()` não fixa `timezone` porque o
parâmetro do ARQ aceita um `datetime.timezone` — deslocamento constante —, e
deslocamento constante erra a virada do horário de verão. O container fixa
`TZ=America/Sao_Paulo` (compose) e o Dockerfile instala `tzdata`.

---

## Desenvolvimento local

```bash
# Stack completa com hot reload (arq --watch)
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up worker scheduler

# Fora do Docker, com Redis local:
pip install -e "apps/worker[dev]"
arq worker.main.WorkerSettings
arq worker.scheduler.SchedulerSettings
```

Conferir o que está registrado, sem subir nada:

```bash
python -c "from arq.worker import get_kwargs; from worker.main import WorkerSettings as W; \
print([f.name for f in get_kwargs(W)['functions']])"
python -c "from arq.worker import get_kwargs; from worker.scheduler import SchedulerSettings as S; \
print([c.name for c in get_kwargs(S)['cron_jobs']])"
```

## Verificação

```bash
ruff check apps/worker && ruff format --check apps/worker
mypy apps packages          # a partir da raiz do monorepo, como o CI faz
pytest apps/worker/tests -q
```
