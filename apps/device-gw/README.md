# apps/device-gw — gateway dos terminais Control iD

Serviço FastAPI que fala o protocolo dos coletores **Control iD** (iDFace,
iDBlock) de um lado e chama a API interna do outro. Rota pública:
`dev.ponto.<dominio>` (ver `infra/docker-compose.yml`).

Isolado da API principal **de propósito** (`PROJETO.md` §11.1): quarenta
terminais religando depois de uma queda de rede e despejando o *backlog* de
`access_logs` ao mesmo tempo não podem derrubar a API que o RH está usando.

---

## O que este serviço é, e o que ele não é

O iDFace **não** é o REP-P. O REP-P é o nosso software. O terminal identifica a
pessoa e produz um `access_log`; este gateway recebe (por Push ou Monitor),
converte para marcação canônica e entrega à API — e **é o servidor** quem
atribui o NSR e grava. Nenhuma linha deste serviço atribui NSR, grava marcação
ou toca no AFD.

Quatro fatos que mudam o desenho de quem mexe aqui:

1. **Toda operação sobre o terminal é assíncrona.** Ele vive em LAN sem IP
   público; quem inicia conexão é ele. Mandar trabalho significa enfileirar
   comando para o próximo ciclo de Push. Por isso `PONTO-TERM-004` ("Terminal
   offline, comando enfileirado") é resposta normal, não falha.
2. **A ingestão é idempotente por `numero_serie + access_log_id`.** Push,
   Monitor e catch-up podem entregar o mesmo registro. Marcação duplicada num
   sistema de ponto é problema trabalhista, não inconveniência.
3. **O relógio do equipamento é evidência, nunca fonte de verdade.** O horário
   oficial da marcação é o do servidor; guardar os dois é obrigatório, porque a
   divergência entre eles é o sinal de que o relógio do terminal derivou.
4. **Template biométrico não passa em claro por aqui** (ADR-006). O que
   interessa é o fato "fulano cadastrou face no terminal X", nunca o vetor.

---

## Estado: Fase 0 entrega andaime

| Endpoint | Estado |
|---|---|
| `GET /health` | ✅ **funcional** — não toca dependência |
| `GET /ready` | ✅ **funcional** — verifica Redis e API interna; 503 `PONTO-INT-003` |
| `POST /new_connection.fcgi` | 501 `PONTO-INT-005` — Push, passo 1 |
| `POST /send_response.fcgi` | 501 `PONTO-INT-005` — Push, passo 3 |
| `POST /interno/terminais/{serie}/comandos` | 501 `PONTO-INT-005` — enfileira comando |
| `POST /api/notifications/dao` | 501 `PONTO-INT-005` — Monitor: novo `access_log` |
| `POST /api/notifications/door` | 501 `PONTO-INT-005` — Monitor: porta |
| `POST /api/notifications/catra` | 501 `PONTO-INT-005` — Monitor: giro de catraca |
| `POST /api/notifications/template` | 501 `PONTO-INT-005` — Monitor: credencial |
| `POST /api/notifications/secbox` | 501 `PONTO-INT-005` — Monitor: alarme |
| `POST /api/notifications/operation_mode` | 501 `PONTO-INT-005` — Monitor: modo |
| `GET /interno/terminais/{serie}/marca-dagua` | 501 `PONTO-INT-005` — catch-up |
| `POST /interno/terminais/{serie}/catch-up` | 501 `PONTO-INT-005` — catch-up |

Cada stub carrega, na docstring, o **formato real** da requisição e da resposta,
para que o simulador e os testes da F6 possam ser escritos contra alvo definido.
A implementação é da **F6 — Integração Control iD**.

### Ressalva honesta sobre os caminhos do Push e do Monitor

Quem escolhe o caminho dessas rotas é o **firmware do equipamento**: o terminal
é configurado com um endereço de servidor e concatena o sufixo fixo que o
fabricante definiu. Os sufixos usados aqui seguem a documentação da Control iD,
mas **não foram verificados contra hardware** — `PROJETO.md` §2 registra a
aquisição de um iDFace físico como pré-requisito ainda em aberto.

Ajustá-los na F6 não custa quase nada e **não exige RFC**: o device-gw não
aparece em `packages/contracts/openapi.yaml`. O que não muda sem RFC é o código
de erro devolvido (`errors.yaml`) e o formato da marcação entregue à API.

---

## Estrutura

```
apps/device-gw/
├── Dockerfile              # multi-stage; instala o alias `app.main` na imagem
├── .dockerignore
├── pyproject.toml
├── README.md
├── tests/
│   └── test_andaime_device_gw.py
└── gateway/
    ├── __init__.py
    ├── py.typed
    ├── config.py           # pydantic-settings; mesmos nomes do compose
    ├── log.py              # log estruturado JSON
    ├── erros.py            # RFC 9457 + recorte de errors.yaml
    ├── main.py             # criar_aplicacao() / app
    ├── simulador.py        # esqueleto do simulador de terminal (F6)
    └── rotas/
        ├── __init__.py
        ├── saude.py        # /health e /ready — funcionais
        ├── push.py         # modo Push
        ├── monitor.py      # serviço Monitor
        └── catchup.py      # catch-up por marca d'água
```

### Por que o pacote se chama `gateway`, e não `app`

`apps/api` já é dono do nome de módulo `app`. O CI roda `mypy apps packages` a
partir da raiz do monorepo, e dois pacotes de mesmo nome em árvores diferentes
fazem o mypy **abortar a coleta inteira** (`Duplicate module named "app"`) — não
é aviso, é parada. Como `apps/device-gw` tem hífen no nome, não existe
`__init__.py` intermediário capaz de desempatar.

O `command` de `infra/docker-compose.dev.yml` continua sendo
`uvicorn app.main:app`, palavra por palavra: o `Dockerfile` instala na imagem um
pacote `app` mínimo (em `/opt/alias`, no `PYTHONPATH`) cujo módulo `main`
reexporta `gateway.main:app`. O alias vive só na imagem; o repositório nunca tem
dois pacotes `app`, e o hot reload continua funcionando porque o uvicorn observa
`/app`, onde o bind mount coloca o código.

---

## Desenvolvimento local

```bash
# Stack completa, com simulador ligado (CONTROLID_SIMULADOR=true no override)
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up device-gw
# Porta publicada: http://localhost:8001  (DEVICE_GW_PORT)

# Fora do Docker:
pip install -e "apps/device-gw[dev]"
uvicorn gateway.main:app --reload
```

## Verificação

```bash
python -c "from gateway.main import app; print(len(app.routes))"
ruff check apps/device-gw && ruff format --check apps/device-gw
mypy apps packages          # a partir da raiz do monorepo, como o CI faz
pytest apps/device-gw/tests -q
```
