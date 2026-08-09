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

## Estado: motor implementado

| Endpoint | Estado |
|---|---|
| `GET /health` | ✅ **funcional** — não toca disco; é o alvo do healthcheck |
| `GET /ready` | ✅ **funcional** — confere se há peso `.onnx`; 503 `PONTO-INT-003` |
| `POST /enroll` | ✅ detecção + embedding ArcFace 512-d + métricas de qualidade |
| `POST /verificar` | ✅ 1:N por cosseno contra os templates de referência |
| `POST /liveness` | ⚠️ **heurística** multi-quadro — ver a ressalva abaixo |

### Qual modelo, e por quê

Pacote **`buffalo_l`** do InsightFace, sobre **ONNX Runtime CPU**:

| Peso | Papel | Tamanho |
|---|---|---|
| `det_10g.onnx` | detecção (RetinaFace ResNet50) | ~17 MB |
| `w600k_r50.onnx` | reconhecimento (ArcFace ResNet50 @ WebFace600K, 512-d) | ~174 MB |
| `1k3d68` / `2d106det` / `genderage` | **não carregados** (ver abaixo) | ~150 MB |

Três razões, na ordem em que pesaram: **roda em CPU** (a VPS não tem GPU);
**licença aberta e uso consolidado** (código MIT, pesos publicados pelo próprio
projeto); e **não inventa nada** — ArcFace com limiar de cosseno é o arranjo
1:1 mais documentado que existe, o que torna calibrar o limiar engenharia
normal em vez de pesquisa. Descartados: `antelopev2` (pesos com cláusula
não-comercial), dlib/`face_recognition` (precisão inferior) e qualquer SaaS —
este último por decisão fundadora, não por técnica.

**Desempenho medido na VPS** (8 vCPU, sob a carga normal dos outros serviços):
`POST /enroll` com captura de 640×480 leva **~0,7 s** de ponta a ponta (mediana
de 10; p90 ~0,88 s). O primeiro request após cada restart paga ~2,8 s a mais —
é o carregamento preguiçoso dos pesos. Não é tempo real, e é folgadamente
suficiente para uma marcação de ponto.

O serviço carrega só `detection` e `recognition`. `genderage`, `2d106det` e
`1k3d68` somam mais de 140 MB de RAM e latência para produzir gênero, idade e
pose 3D — nada disso entra em decisão de ponto eletrônico, e **gênero e idade
inferidos são dado pessoal que ninguém pediu**: extrair o que não se usa é criar
passivo de LGPD de graça. A métrica de pose do bloco `qualidade` sai da
geometria dos 5 pontos-chave que o detector já devolve.

### Limiar de similaridade

`FACIAL_LIMIAR_SIMILARIDADE`, padrão **0,42** (cosseno). Para ArcFace a faixa
útil de 1:1 com FAR baixo fica entre 0,30 e 0,45; 0,42 fica no lado conservador
dela de propósito — falso positivo em biometria de ponto é fraude trabalhista,
falso negativo é um segundo pedido de nova captura. Os dois erros não custam a
mesma coisa. Medido na suíte (seis identidades reais, duas imagens distintas de
cada): mesma pessoa ≥ 0,90, pessoas diferentes ≤ 0,22.

### Ressalva sobre `/liveness`

O que está implementado é um conjunto de **heurísticas clássicas multi-quadro**
(movimento entre quadros, textura de alta frequência, moiré de tela) — **não** é
um classificador de anti-spoofing treinado. A família `MiniFASNet`
(*Silent-Face-Anti-Spoofing*) publica pesos PyTorch, e as conversões ONNX que
circulam são espelhos de terceiros sem cadeia de custódia: baixar peso
biométrico de repositório não oficial para dentro de uma imagem de produção
troca um risco técnico por um risco de cadeia de suprimentos pior.

Consequência **normativa**: enquanto esta for a única prova de vida do sistema,
o resultado de `/liveness` é **sinal de confiança** (alimenta `peso_biometria`
do ADR-008) e não portão suficiente sozinho. A troca cabe atrás da mesma
função (`julgar_liveness`) sem mexer no contrato HTTP.

### Por que `/health` não confere os pesos

A `api` declara `depends_on: facial-svc: condition: service_healthy`. Se
`/health` reprovasse por falta de peso `.onnx`, um volume `facial-models` vazio
prenderia a **stack inteira** no `depends_on` — a API nem subiria para dizer o
que está errado. Do jeito que está, o serviço sobe, responde `/health`, reprova
em `/ready` e **diz** que faltam os pesos.

---

## Pesos do modelo — download na primeira execução, e o que fazemos com isso

Os arquivos `.onnx` **não entram na imagem e não entram no git**: são ~326 MB e
têm ciclo de vida próprio. Chegam pelo volume `facial-models`, montado em
`/models` (`FACIAL_MODEL_DIR`), no layout do InsightFace:
`/models/buffalo_l/*.onnx`.

O comportamento padrão do `insightface` é **baixar o pacote do GitHub na
primeira execução**. Isso tem implicação direta de build de imagem, e a escolha
foi feita explicitamente:

| Opção | Veredito |
|---|---|
| Baixar em **runtime** | ❌ faz uma marcação de ponto depender de repositório de terceiro estar no ar, soma ~30 s ao primeiro request após cada restart, e aceita como válido o peso que aquele repositório servir naquele dia |
| Baixar no **build** da imagem | ❌ 326 MB em cada tag, `docker build` do CI passa a depender de rede externa, e amarra o ciclo de vida dos pesos ao das releases de código |
| **Volume**, populado por passo explícito de deploy | ✅ **escolhido** — pesos viram artefato versionado e verificável por hash, imagem continua enxuta, e trocar o motor deixa de exigir rebuild |

Por isso `FACIAL_BAIXAR_MODELO` é **falso por padrão**, e a própria
`Configuracao` **recusa** ligá-lo em `hml`/`prd` (levanta na validação, não
avisa). Em `dev`/`ci` a conveniência ganha: ligue e o InsightFace popula
`/models` sozinho.

```bash
# dev/ci: deixar o próprio serviço baixar
FACIAL_BAIXAR_MODELO=1 uvicorn facial.main:app

# deploy: popular o volume a partir de um artefato já baixado e conferido
docker run --rm -v ponto-facial-models:/models -v "$PWD/pesos:/origem" \
  alpine sh -c "cp -r /origem/buffalo_l /models/"
```

Fora do container, o padrão dos testes é `~/.insightface/models` (a convenção do
próprio InsightFace).

### `FACIAL_MODEL_VERSAO` precisa descrever o modelo que está carregado

O default deixou de ser `arcface-r100-v1` e passou a ser
`buffalo_l-w600k_r50-v1`: o reconhecedor do `buffalo_l` é um ResNet**50**, não
um R100. Carimbo que descreve um modelo que não é o carregado é pior que carimbo
nenhum — ele mente com aparência de rastreabilidade, e é justamente esse carimbo
que `biometria_templates.versao_modelo` usa para decidir o que é comparável com
o quê. `POST /verificar` **recusa** (`400 PONTO-VAL-001`) templates carimbados
com outra versão.

---

## Estrutura

```
apps/facial-svc/
├── Dockerfile              # multi-stage; instala o alias `app.main` na imagem
├── .dockerignore
├── pyproject.toml
├── README.md
├── tests/
│   ├── conftest.py                 # AMBIENTE=ci e FACIAL_BAIXAR_MODELO antes do import
│   ├── test_andaime_facial_svc.py  # contrato, catálogo de erros, healthchecks
│   └── test_motor_facial.py        # pipeline real: detecção → embedding → veredito
└── facial/
    ├── __init__.py
    ├── py.typed
    ├── config.py           # pydantic-settings; mesmos nomes do compose
    ├── log.py              # log estruturado JSON, sem nenhum dado biométrico
    ├── erros.py            # RFC 9457 + recorte de errors.yaml
    ├── esquemas.py         # contrato Pydantic das três operações
    ├── main.py             # criar_aplicacao() / app
    ├── motor/              # ÚNICA parte que carrega peso ONNX
    │   ├── __init__.py
    │   ├── imagem.py       # base64 → BGR, com tipo e tamanho antes da decodificação
    │   ├── arcface.py      # InsightFace/ONNX: detecção, embedding, qualidade
    │   ├── template.py     # serialização do vetor + similaridade de cosseno
    │   └── liveness.py     # prova de vida heurística (ver ressalva)
    └── rotas/
        ├── __init__.py
        ├── saude.py        # /health e /ready
        └── biometria.py    # /enroll, /verificar, /liveness — não importa numpy/cv2
```

`facial/rotas/biometria.py` **não importa numpy, OpenCV nem InsightFace**. A
fronteira é `facial.motor`, e ela existe para que trocar o motor — decisão
prevista, e a razão de `modeloVersao` existir — não encoste no contrato HTTP.

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

# A suíte do motor exige os pesos. Sem eles (e sem FACIAL_BAIXAR_MODELO), ela
# é PULADA — nunca aprovada em silêncio.
FACIAL_MODEL_DIR=~/.insightface/models FACIAL_BAIXAR_MODELO=1 \
  pytest apps/facial-svc/tests -q
```

`tests/test_motor_facial.py` roda o pipeline de ponta a ponta contra **rostos
reais**: usa a foto de grupo `t1` que acompanha o próprio pacote `insightface`
(repositório MIT), que tem seis pessoas distintas. Nenhuma imagem de rosto entra
no repositório da SEEG — ela vem da dependência, em tempo de execução. De cada
pessoa a suíte deriva duas imagens diferentes (margens, escalas e qualidades
JPEG distintas), e prova: **mesma pessoa aprova com o índice certo entre seis
templates; pessoas diferentes reprovam nas 30 comparações cruzadas; imagem sem
rosto vira `400 PONTO-VAL-001` em `problem+json`**.
