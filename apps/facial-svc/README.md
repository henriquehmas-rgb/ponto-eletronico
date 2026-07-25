# apps/facial-svc — serviço facial self-hosted

Wrapper HTTP do motor **`analise-facial-edge`** (InsightFace / ArcFace ONNX),
reaproveitado conforme a decisão **D4** de `PROJETO.md`.

A escolha não é só econômica. Não há custo por chamada, e — o que decide — **a
biometria não sai da infraestrutura da SEEG**: mandar rosto de colaborador para
nuvem alheia é tratamento de dado pessoal sensível por operador que o titular
nunca autorizou (LGPD art. 5º, II, e ADR-006).

Por isso o serviço é **interno por definição**: `infra/docker-compose.yml` o
mantém só na rede `ponto-interna`, sem rota no Traefik e com
`traefik.enable: "false"` explícito.

---

## Cinco regras que este serviço existe para cumprir

1. **Imagem crua nunca é persistida.** Ela entra, vira vetor e é descartada
   (ADR-006, item 4). Nada de arquivo temporário em disco "só para depurar": em
   serviço biométrico, arquivo temporário é vazamento com data marcada. Se a
   política do cliente exigir reter a imagem para contestação, quem guarda é o
   MinIO — cifrado, com prazo curto, expurgo automático, e nunca por padrão.
2. **O vetor é versionado pelo modelo.** Toda resposta de `/enroll` carrega
   `modeloVersao`. Vetores de motores diferentes não são comparáveis; sem esse
   carimbo, trocar o motor invalidaria a base biométrica inteira em silêncio.
3. **O vetor nunca vaza em log nem em mensagem de erro.** Ele sai no corpo da
   resposta, para quem cifra, e só.
4. **O limiar de similaridade nunca aparece em resposta.** Os `PONTO-SCORE-*`
   têm `expoe_regra: false` em `errors.yaml`. Responder "similaridade 0,39,
   limiar 0,42" a quem está testando máscara impressa entrega o mapa da fraude:
   a pessoa passa a saber exatamente quanto falta e itera até acertar.
5. **Este serviço não tem credencial de banco.** Repare no compose: `facial-svc`
   é o único serviço Python que **não** entra no bloco `x-python-env` — não
   recebe `DATABASE_URL`, `REDIS_URL` nem chave do MinIO. Serviço que não tem
   credencial não vaza credencial, mesmo comprometido.

---

## Estado: Fase 0 entrega andaime

| Endpoint | Estado |
|---|---|
| `GET /health` | ✅ **funcional** — não toca disco; é o alvo do healthcheck |
| `GET /ready` | ✅ **funcional** — confere se há peso `.onnx`; 503 `PONTO-INT-003` |
| `POST /enroll` | 501 `PONTO-INT-005` — extração de template (F2) |
| `POST /verificar` | 501 `PONTO-INT-005` — comparação contra templates (F2) |
| `POST /liveness` | 501 `PONTO-INT-005` — prova de vida (F7) |

Cada stub carrega, na docstring, o **contrato de entrada e de saída** previsto,
para que o chamador da F2 e da F7 possa ser escrito e testado com dublê.

**O motor não é carregado neste estado.** Não há `import onnxruntime`, e
`onnxruntime`, `insightface`, `numpy` e `opencv` **não estão declarados** no
`pyproject.toml`. Declarar biblioteca pesada antes de existir código que a use
só faria a imagem crescer e o build do CI demorar. Elas entram na F2, junto com
o código que as chama.

### Por que `/health` não confere os pesos

A `api` declara `depends_on: facial-svc: condition: service_healthy`. Se
`/health` reprovasse por falta de peso `.onnx`, um volume `facial-models` vazio
prenderia a **stack inteira** no `depends_on` — a API nem subiria para dizer o
que está errado. Do jeito que está, o serviço sobe, responde `/health`, reprova
em `/ready` e **diz** que faltam os pesos.

---

## Pesos do modelo

Os arquivos `.onnx` **não entram na imagem e não entram no git**: são grandes e
têm ciclo de vida próprio. Chegam pelo volume `facial-models`, montado em
`/models` (`FACIAL_MODEL_DIR`).

```bash
# Popular o volume em desenvolvimento (exemplo)
docker run --rm -v ponto-facial-models:/models -v "$PWD/pesos:/origem" \
  alpine sh -c "cp /origem/*.onnx /models/"
```

---

## Estrutura

```
apps/facial-svc/
├── Dockerfile              # multi-stage; instala o alias `app.main` na imagem
├── .dockerignore
├── pyproject.toml
├── README.md
├── tests/
│   └── test_andaime_facial_svc.py
└── facial/
    ├── __init__.py
    ├── py.typed
    ├── config.py           # pydantic-settings; mesmos nomes do compose
    ├── log.py              # log estruturado JSON, sem nenhum dado biométrico
    ├── erros.py            # RFC 9457 + recorte de errors.yaml
    ├── main.py             # criar_aplicacao() / app
    └── rotas/
        ├── __init__.py
        ├── saude.py        # /health e /ready — funcionais
        └── biometria.py    # /enroll, /verificar, /liveness — stubs 501
```

### Por que o pacote se chama `facial`, e não `app`

`apps/api` já é dono do nome de módulo `app`. O CI roda `mypy apps packages` a
partir da raiz do monorepo, e dois pacotes de mesmo nome em árvores diferentes
fazem o mypy **abortar a coleta inteira** (`Duplicate module named "app"`) — não
é aviso, é parada. Como `apps/facial-svc` tem hífen no nome, não existe
`__init__.py` intermediário capaz de desempatar.

O `command` de `infra/docker-compose.dev.yml` continua sendo
`uvicorn app.main:app`, palavra por palavra: o `Dockerfile` instala na imagem um
pacote `app` mínimo (em `/opt/alias`, no `PYTHONPATH`) cujo módulo `main`
reexporta `facial.main:app`.

---

## Desenvolvimento local

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up facial-svc
# Porta publicada: http://localhost:8010  (FACIAL_PORT)

# Fora do Docker:
pip install -e "apps/facial-svc[dev]"
uvicorn facial.main:app --reload
```

## Verificação

```bash
python -c "from facial.main import app; print(len(app.routes))"
ruff check apps/facial-svc && ruff format --check apps/facial-svc
mypy apps packages          # a partir da raiz do monorepo, como o CI faz
pytest apps/facial-svc/tests -q
```
