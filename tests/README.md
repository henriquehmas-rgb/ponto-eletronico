# tests/ — testes de sistema do monorepo

Este diretório existe desde a Fase 0 por dois motivos concretos:

1. **PROJETO.md §11.3** declara `tests/` como parte do layout do monorepo
   (e2e, carga, fixtures legais de AFD/AEJ de referência).
2. **`.github/workflows/ci.yml`** roda `ruff check apps packages tests` e
   `ruff format --check --diff apps packages tests`. Com o caminho ausente o
   ruff aborta com `E902` e o CI fica vermelho por falta de diretório, não por
   defeito de código.

Testes que vivem **dentro** de uma app continuam na app: `apps/api/tests/` é o
lugar dos testes da API. Aqui ficam apenas os testes que atravessam mais de um
serviço.

## Conteúdo previsto (nenhum deles é da Fase 0)

| Caminho | Fase | O que guarda |
|---|---|---|
| `tests/e2e/` | F8, F10, F15 | Playwright (web) e fluxos ponta a ponta |
| `tests/carga/` | F15 | roteiros k6 (500 marcações simultâneas) |
| `tests/fixtures/legais/` | F3, F12 | golden dataset trabalhista e AFD/AEJ de referência |

A Fase 0 é contrato e andaime: nenhum teste de negócio nasce aqui. Os testes do
andaime da API estão em `apps/api/tests/test_andaime.py`.
